"""La cuenta de práctica: dinero ficticio, libro real, reglas de verdad.

Contra una `FuenteFalsa` con un libro hecho a mano: compras y ventas a mercado nivel a nivel, órdenes
con límite que apartan saldo y se ejecutan al cruzar, lo que no se deja hacer (sin saldo, sin
moneda, sin libro, sin conexión), el reinicio y que todo sobrevive a cerrar y volver a abrir.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from invest_ll.vivo.ejecucion import Comisiones
from invest_ll.vivo.fuente import FuenteFalsa, Libro, Nivel
from invest_ll.vivo.practica import (
    INICIAL,
    CuentaDePractica,
    OrdenNoEncontradaError,
    PracticaError,
    SinConexionError,
    SinLibroError,
    SinMonedaError,
    SinSaldoError,
)

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path

D = Decimal
AHORA = datetime(2026, 10, 17, 18, 0, tzinfo=UTC)
SIN_COMISION = Comisiones(tomador=D(0), creador=D(0))


def libro(
    compras: list[tuple[str, str]], ventas: list[tuple[str, str]], coin: str = "BTC"
) -> Libro:
    return Libro(
        coin=coin,
        compras=tuple(Nivel(D(p), D(c)) for p, c in compras),
        ventas=tuple(Nivel(D(p), D(c)) for p, c in ventas),
        at=AHORA,
    )


LIBRO_BTC = libro(
    compras=[("99", "1"), ("98", "2"), ("97", "5")],
    ventas=[("100", "1"), ("101", "2"), ("102", "5")],
)


@pytest.fixture
def fuente() -> FuenteFalsa:
    return FuenteFalsa(libros={"BTC": LIBRO_BTC})


def cuenta_en(carpeta: Path, comisiones: Comisiones = SIN_COMISION) -> CuentaDePractica:
    return CuentaDePractica(carpeta, reloj=lambda: AHORA, comisiones=comisiones)


@pytest.fixture
def cuenta(tmp_path: Path) -> CuentaDePractica:
    return cuenta_en(tmp_path / "practica")


def test_empieza_con_diez_mil_y_sin_tocar_el_disco(tmp_path: Path) -> None:
    cuenta = cuenta_en(tmp_path / "practica")
    foto = cuenta.foto()
    assert (foto.inicial, foto.saldo, foto.reservado) == (INICIAL, D(10000), D(0))
    assert foto.posiciones == foto.ordenes == foto.historial == ()
    assert not (tmp_path / "practica").exists()


def test_comprar_a_mercado_recorre_el_libro(cuenta: CuentaDePractica, fuente: FuenteFalsa) -> None:
    resultado = cuenta.a_mercado(fuente, "BTC", "compra", cantidad=D(2))
    hecha = resultado.ejecutada
    assert hecha is not None
    assert (hecha.cantidad, hecha.importe, hecha.precio) == (D(2), D(201), D("100.5"))
    foto = cuenta.foto()
    assert foto.saldo == D(10000) - D(201)
    assert foto.posiciones[0].cantidad == D(2)
    assert foto.posiciones[0].precio_medio == D("100.5")
    assert resultado.resumen.startswith("Compraste 2 Bitcoin a 100,50 USDC de media")


def test_la_comision_se_paga_y_entra_en_el_precio_medio(
    tmp_path: Path, fuente: FuenteFalsa
) -> None:
    cuenta = cuenta_en(tmp_path, Comisiones(tomador=D("0.001"), creador=D(0)))
    hecha = cuenta.a_mercado(fuente, "BTC", "compra", cantidad=D(1)).ejecutada
    assert hecha is not None
    assert hecha.comision == D("0.1")
    assert cuenta.foto().saldo == D("9899.9")
    assert cuenta.foto().posiciones[0].precio_medio == D("100.1")


def test_comprar_por_importe_recorta_a_los_decimales_de_la_moneda(
    cuenta: CuentaDePractica, fuente: FuenteFalsa
) -> None:
    hecha = cuenta.a_mercado(fuente, "BTC", "compra", importe=D(150), decimales=2).ejecutada
    assert hecha is not None
    # 150 USDC: 1 a 100 y 0,495 a 101 son 1,495..., que con 2 decimales se queda en 1,49.
    assert hecha.cantidad == D("1.49")
    assert hecha.importe == D(100) + D("0.49") * 101


def test_vender_lo_que_tienes_y_no_mas(cuenta: CuentaDePractica, fuente: FuenteFalsa) -> None:
    with pytest.raises(SinMonedaError, match="No tienes Bitcoin"):
        cuenta.a_mercado(fuente, "BTC", "venta", cantidad=D(1))
    cuenta.a_mercado(fuente, "BTC", "compra", cantidad=D(2))
    with pytest.raises(SinMonedaError, match="Solo tienes 2 de Bitcoin"):
        cuenta.a_mercado(fuente, "BTC", "venta", cantidad=D(3))
    venta = cuenta.a_mercado(fuente, "BTC", "venta", cantidad=D("1.5"))
    hecha = venta.ejecutada
    assert hecha is not None
    assert hecha.importe == D(99) + D("0.5") * 98
    assert "Vendiste 1,5 Bitcoin" in venta.resumen
    foto = cuenta.foto()
    assert foto.posiciones[0].cantidad == D("0.5")
    assert foto.posiciones[0].precio_medio == D("100.5")  # vender no cambia el precio medio
    cuenta.a_mercado(fuente, "BTC", "venta", cantidad=D("0.5"))
    assert cuenta.foto().posiciones == ()


def test_sin_saldo_no_se_compra(cuenta: CuentaDePractica) -> None:
    caro = FuenteFalsa(libros={"BTC": libro([("99999", "1")], [("100000", "1")])})
    with pytest.raises(SinSaldoError, match=r"No te llega: son 100\.000,00 USDC"):
        cuenta.a_mercado(caro, "BTC", "compra", cantidad=D(1))
    assert cuenta.foto().saldo == D(10000)


def test_todo_el_saldo_se_ajusta_para_que_quepa_la_comision(tmp_path: Path) -> None:
    cuenta = cuenta_en(tmp_path, Comisiones(tomador=D("0.00045"), creador=D(0)))
    grande = FuenteFalsa(libros={"BTC": libro([("99", "1000")], [("100", "1000")])})
    resultado = cuenta.a_mercado(grande, "BTC", "compra", importe=D(10000), decimales=5)
    assert resultado.ajustada
    assert "Ajustada para que la comisión quepa" in resultado.resumen
    saldo = cuenta.foto().saldo
    assert D(0) <= saldo < D("0.01")


def test_sin_libro_lo_pide_y_no_inventa(cuenta: CuentaDePractica) -> None:
    vacia = FuenteFalsa(precios={"ETH": D(2400)})
    with pytest.raises(SinLibroError, match="Aún no hay libro de Ethereum, prueba en un segundo"):
        cuenta.a_mercado(vacia, "ETH", "compra", cantidad=D(1))
    assert ("ETH", True, ()) in vacia.seguidas


def test_sin_conexion_no_se_opera_con_precios_viejos(cuenta: CuentaDePractica) -> None:
    caida = FuenteFalsa(libros={"BTC": LIBRO_BTC}, conectada_=False)
    with pytest.raises(SinConexionError):
        cuenta.a_mercado(caida, "BTC", "compra", cantidad=D(1))


def test_libro_insuficiente_no_inventa_precio(
    cuenta: CuentaDePractica, fuente: FuenteFalsa
) -> None:
    with pytest.raises(PracticaError, match="solo tiene 8"):
        cuenta.a_mercado(fuente, "BTC", "compra", cantidad=D(9))


def test_cantidad_e_importe_a_la_vez_no(cuenta: CuentaDePractica, fuente: FuenteFalsa) -> None:
    with pytest.raises(PracticaError, match="uno de los dos"):
        cuenta.a_mercado(fuente, "BTC", "compra", cantidad=D(1), importe=D(100))
    with pytest.raises(PracticaError, match="demasiado pequeña"):
        cuenta.a_mercado(fuente, "BTC", "compra", cantidad=D("0.001"), decimales=2)


# -- Órdenes con límite --------------------------------------------------------------------------


def test_compra_con_limite_aparta_saldo_y_se_ejecuta_al_cruzar(
    tmp_path: Path, fuente: FuenteFalsa
) -> None:
    cuenta = cuenta_en(tmp_path, Comisiones(tomador=D("0.00045"), creador=D("0.00015")))
    resultado = cuenta.con_limite(fuente, "BTC", "compra", cantidad=D(2), precio_limite=D(95))
    orden = resultado.orden
    assert orden is not None and resultado.ejecutada is None
    assert orden.reservado == D(190) + D("0.0285")
    assert "Se apartan 190,03 USDC" in resultado.resumen
    foto = cuenta.foto()
    assert foto.reservado == orden.reservado
    assert foto.saldo == D(10000) - orden.reservado
    assert ("BTC", True, ()) in fuente.seguidas

    assert cuenta.revisar(fuente) == []  # el libro aún no la cruza (venta más barata: 100)
    fuente.libros["BTC"] = libro([("94", "1")], [("95", "3")])
    hechas = cuenta.revisar(fuente)
    assert len(hechas) == 1
    hecha = hechas[0]
    assert (hecha.precio, hecha.cantidad, hecha.tipo, hecha.orden_id) == (
        D(95),
        D(2),
        "limite",
        orden.id,
    )
    assert hecha.comision == D("0.0285")  # de creador
    foto = cuenta.foto()
    assert foto.ordenes == ()
    assert foto.reservado == D(0)
    assert foto.saldo == D(10000) - D(190) - D("0.0285")
    assert foto.posiciones[0].cantidad == D(2)
    assert cuenta.revisar(fuente) == []  # no se ejecuta dos veces


def test_venta_con_limite_aparta_la_moneda(cuenta: CuentaDePractica, fuente: FuenteFalsa) -> None:
    cuenta.a_mercado(fuente, "BTC", "compra", cantidad=D(1))
    cuenta.con_limite(fuente, "BTC", "venta", cantidad=D("0.6"), precio_limite=D(110))
    assert cuenta.disponible("BTC") == D("0.4")
    with pytest.raises(SinMonedaError, match="Solo tienes 0,4"):
        cuenta.a_mercado(fuente, "BTC", "venta", cantidad=D("0.5"))
    fuente.libros["BTC"] = libro([("111", "5")], [("112", "5")])
    hecha = cuenta.revisar(fuente)[0]
    assert (hecha.lado, hecha.precio, hecha.cantidad) == ("venta", D(110), D("0.6"))
    assert cuenta.foto().posiciones[0].cantidad == D("0.4")


def test_limite_que_ya_cruza_se_ejecuta_como_tomador_sin_pasar_de_su_precio(
    cuenta: CuentaDePractica, fuente: FuenteFalsa
) -> None:
    resultado = cuenta.con_limite(fuente, "BTC", "compra", cantidad=D(2), precio_limite=D(101))
    hecha = resultado.ejecutada
    assert hecha is not None and resultado.orden is None
    assert hecha.importe == D(201)  # 1 a 100 y 1 a 101: lo del libro, no su límite
    assert resultado.resumen.startswith("Tu precio ya cruzaba el libro")
    with pytest.raises(PracticaError, match="hasta ese precio no hay bastante"):
        cuenta.con_limite(fuente, "BTC", "compra", cantidad=D(4), precio_limite=D(101))


def test_limite_sin_saldo_o_sin_moneda(cuenta: CuentaDePractica, fuente: FuenteFalsa) -> None:
    with pytest.raises(SinSaldoError):
        cuenta.con_limite(fuente, "BTC", "compra", cantidad=D(200), precio_limite=D(90))
    with pytest.raises(SinMonedaError):
        cuenta.con_limite(fuente, "BTC", "venta", cantidad=D(1), precio_limite=D(200))


def test_cancelar_devuelve_lo_apartado(cuenta: CuentaDePractica, fuente: FuenteFalsa) -> None:
    orden = cuenta.con_limite(fuente, "BTC", "compra", cantidad=D(1), precio_limite=D(90)).orden
    assert orden is not None
    cuenta.cancelar(orden.id)
    foto = cuenta.foto()
    assert (foto.saldo, foto.reservado, foto.ordenes) == (D(10000), D(0), ())
    with pytest.raises(OrdenNoEncontradaError):
        cuenta.cancelar(orden.id)


def test_sin_conexion_las_ordenes_esperan(cuenta: CuentaDePractica, fuente: FuenteFalsa) -> None:
    cuenta.con_limite(fuente, "BTC", "compra", cantidad=D(1), precio_limite=D(95))
    fuente.libros["BTC"] = libro([("90", "1")], [("91", "3")])
    fuente.conectada_ = False
    assert cuenta.revisar(fuente) == []
    fuente.conectada_ = True
    assert len(cuenta.revisar(fuente)) == 1


# -- En disco ------------------------------------------------------------------------------------


def test_todo_sobrevive_a_cerrar_y_abrir(tmp_path: Path, fuente: FuenteFalsa) -> None:
    carpeta = tmp_path / "practica"
    cuenta = cuenta_en(carpeta, Comisiones(tomador=D("0.00045"), creador=D("0.00015")))
    cuenta.a_mercado(fuente, "BTC", "compra", cantidad=D(3))
    cuenta.a_mercado(fuente, "BTC", "venta", cantidad=D(1))
    cuenta.con_limite(fuente, "BTC", "compra", cantidad=D(1), precio_limite=D(90))
    vendida = cuenta.con_limite(fuente, "BTC", "venta", cantidad=D(1), precio_limite=D(120)).orden
    assert vendida is not None
    cuenta.cancelar(vendida.id)
    antes = cuenta.foto()

    otra = cuenta_en(carpeta)
    assert otra.foto() == antes

    lineas = (carpeta / "registro.jsonl").read_text(encoding="utf-8").splitlines()
    hechos = [json.loads(linea)["hecho"] for linea in lineas]
    assert hechos == ["inicio", "ejecucion", "ejecucion", "orden", "orden", "cancelacion"]
    assert not [p for p in carpeta.iterdir() if p.name.startswith(".tmp")]


def test_el_registro_solo_crece(tmp_path: Path, fuente: FuenteFalsa) -> None:
    carpeta = tmp_path / "practica"
    cuenta = cuenta_en(carpeta)
    cuenta.a_mercado(fuente, "BTC", "compra", cantidad=D(1))
    primero = (carpeta / "registro.jsonl").read_text(encoding="utf-8")
    cuenta.a_mercado(fuente, "BTC", "venta", cantidad=D(1))
    segundo = (carpeta / "registro.jsonl").read_text(encoding="utf-8")
    assert segundo.startswith(primero)
    assert len(segundo.splitlines()) == len(primero.splitlines()) + 1


def test_si_no_se_puede_escribir_la_cuenta_no_cambia(
    cuenta: CuentaDePractica, fuente: FuenteFalsa, monkeypatch: pytest.MonkeyPatch
) -> None:
    def falla(*_: object) -> None:
        raise OSError("disco lleno")

    monkeypatch.setattr("invest_ll.vivo.practica.os.replace", falla)
    with pytest.raises(OSError, match="disco lleno"):
        cuenta.a_mercado(fuente, "BTC", "compra", cantidad=D(1))
    assert cuenta.foto().saldo == D(10000)
    assert cuenta.foto().historial == ()


def test_reiniciar_guarda_la_cuenta_anterior_aparte(tmp_path: Path, fuente: FuenteFalsa) -> None:
    carpeta = tmp_path / "practica"
    cuenta = cuenta_en(carpeta)
    cuenta.a_mercado(fuente, "BTC", "compra", cantidad=D(1))
    anterior = (carpeta / "registro.jsonl").read_text(encoding="utf-8")
    guardado = cuenta.reiniciar(D(50000))
    assert guardado is not None
    assert guardado.parent == carpeta / "anteriores"
    assert guardado.read_text(encoding="utf-8") == anterior
    foto = cuenta.foto()
    assert (foto.inicial, foto.saldo, foto.posiciones, foto.historial) == (
        D(50000),
        D(50000),
        (),
        (),
    )
    assert cuenta_en(carpeta).foto() == foto
    with pytest.raises(PracticaError):
        cuenta.reiniciar(D(0))


def test_una_linea_rota_del_registro_se_salta(tmp_path: Path, fuente: FuenteFalsa) -> None:
    carpeta = tmp_path / "practica"
    cuenta = cuenta_en(carpeta)
    cuenta.a_mercado(fuente, "BTC", "compra", cantidad=D(1))
    with (carpeta / "registro.jsonl").open("a", encoding="utf-8") as registro:
        registro.write("{esto no es json\n")
    assert cuenta_en(carpeta).foto() == cuenta.foto()

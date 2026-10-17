"""`/api/practica`: la cuenta de práctica por la API, con una `FuenteFalsa` y sin red.

Las reglas finas (redondeos, comisiones, el registro) las prueba `tests/unit/test_vivo_practica.py`;
aquí, que la API las sirve como promete el contrato: valoración a precios de ahora, 422 en llano,
404 al cancelar lo que no existe, y la cuenta en `practica/` del directorio de trabajo.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from invest_ll.vivo import servicio
from invest_ll.vivo.fuente import FuenteFalsa, Libro, Nivel

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterator

    from .api_apoyo import Api

D = Decimal
AHORA = datetime(2026, 10, 17, 18, 0, tzinfo=UTC)


def libro(compra: str, venta: str, cantidad: str = "10") -> Libro:
    return Libro(
        coin="BTC",
        compras=(Nivel(D(compra), D(cantidad)),),
        ventas=(Nivel(D(venta), D(cantidad)),),
        at=AHORA,
    )


@pytest.fixture
def fuente(monkeypatch: pytest.MonkeyPatch) -> Iterator[FuenteFalsa]:
    falsa = FuenteFalsa(libros={"BTC": libro("99", "100")})
    servicio.usar_fuente(falsa)
    monkeypatch.setattr(servicio, "ahora", lambda: AHORA)
    yield falsa
    servicio.usar_fuente(None)


def test_cuenta_nueva(cliente: Api, fuente: FuenteFalsa) -> None:
    cuenta = cliente.get("/api/practica").json()
    assert cuenta == {
        "inicial": "10000",
        "saldo": "10000",
        "reservado": "0",
        "valor_total": "10000",
        "ganancia": "0",
        "ganancia_pct": 0.0,
        "posiciones": [],
        "ordenes": [],
        "historial": [],
        "at": "2026-10-17T18:00:00Z",
    }
    assert not Path("practica").exists()  # mirar no escribe nada


def test_comprar_y_vender_a_mercado(cliente: Api, fuente: FuenteFalsa) -> None:
    compra = cliente.post(
        "/api/practica/ordenes",
        json={"coin": "BTC", "lado": "compra", "tipo": "mercado", "importe": "1000"},
    )
    assert compra.status_code == 200, compra.text
    datos = compra.json()
    assert datos["resumen"] == (
        "Compraste 10 Bitcoin a 100,00 USDC de media: 1.000,00 USDC más 0,45 USDC de comisión."
    )
    assert datos["orden"] is None
    ejecucion = datos["ejecucion"]
    assert (ejecucion["cantidad"], ejecucion["importe"], ejecucion["tipo"]) == (
        "10",
        "1000",
        "mercado",
    )
    assert ejecucion["comision"] == "0.45"
    assert ejecucion["nombre"] == "Bitcoin"
    cuenta = datos["cuenta"]
    assert cuenta["saldo"] == "8999.55"
    [posicion] = cuenta["posiciones"]
    assert posicion["precio"] == "99.5"  # el medio del libro de ahora
    assert posicion["valor"] == "995"
    assert D(posicion["ganancia"]) == D("995") - D("1000.45")
    assert D(cuenta["valor_total"]) == D("8999.55") + D("995")

    fuente.libros["BTC"] = libro("110", "111")
    venta = cliente.post(
        "/api/practica/ordenes",
        json={"coin": "BTC", "lado": "venta", "tipo": "mercado", "cantidad": "4"},
    ).json()
    assert venta["resumen"].startswith("Vendiste 4 Bitcoin a 110,00 USDC de media: cobras")
    assert venta["cuenta"]["posiciones"][0]["cantidad"] == "6"
    historial = venta["cuenta"]["historial"]
    assert [h["lado"] for h in historial] == ["venta", "compra"]  # la más reciente primero
    assert Path("practica/registro.jsonl").exists()


def test_lo_que_no_se_puede_es_422_en_llano(cliente: Api, fuente: FuenteFalsa) -> None:
    def orden(**campos: str) -> tuple[int, str]:
        respuesta = cliente.post("/api/practica/ordenes", json=campos)
        return respuesta.status_code, respuesta.json()["detail"]

    assert orden(coin="BTC", lado="venta", tipo="mercado", cantidad="1") == (
        422,
        "No tienes Bitcoin para vender.",
    )
    codigo, texto = orden(coin="BTC", lado="compra", tipo="mercado", cantidad="1000")
    assert codigo == 422
    assert texto.startswith("No te llega") or texto.startswith("El libro de BTC solo tiene")
    assert orden(coin="ETH", lado="compra", tipo="mercado", cantidad="1") == (
        422,
        "Aún no hay libro de Ethereum, prueba en un segundo.",
    )
    assert ("ETH", True, ()) in fuente.seguidas
    assert orden(coin="BTC", lado="compra", tipo="limite", importe="100", precio_limite="90")[
        1
    ].startswith("Una orden con límite se da en cantidad")
    assert orden(coin="BTC", lado="compra", tipo="limite", cantidad="1")[1] == (
        "Una orden con límite necesita la cantidad y el precio límite."
    )
    assert orden(coin="BTC", lado="compra", tipo="mercado", cantidad="1", precio_limite="90")[
        1
    ].startswith("Una orden a mercado no lleva precio límite")
    assert orden(coin="BTC", lado="compra", tipo="mercado")[1] == (
        "Di la cantidad (en la moneda) o el importe (en USDC), uno de los dos."
    )
    codigo, texto = orden(coin="BTC", lado="compra", tipo="mercado", cantidad="-1")
    assert codigo == 422
    assert "cantidad" in texto
    assert cliente.get("/api/practica").json()["saldo"] == "10000"


def test_sin_conexion_no_se_opera(cliente: Api, fuente: FuenteFalsa) -> None:
    fuente.conectada_ = False
    respuesta = cliente.post(
        "/api/practica/ordenes",
        json={"coin": "BTC", "lado": "compra", "tipo": "mercado", "cantidad": "1"},
    )
    assert respuesta.status_code == 422
    assert "no se opera con precios viejos" in respuesta.json()["detail"]


def test_orden_con_limite_se_ejecuta_al_cruzar_y_otra_se_cancela(
    cliente: Api, fuente: FuenteFalsa
) -> None:
    primera = cliente.post(
        "/api/practica/ordenes",
        json={
            "coin": "BTC",
            "lado": "compra",
            "tipo": "limite",
            "cantidad": "1",
            "precio_limite": "95",
        },
    ).json()
    orden = primera["orden"]
    assert primera["ejecucion"] is None
    assert orden["precio_limite"] == "95"
    assert primera["cuenta"]["reservado"] == "95.01425"
    assert primera["resumen"].startswith("Orden puesta: comprar 1 Bitcoin cuando alguien venda")
    segunda = cliente.post(
        "/api/practica/ordenes",
        json={
            "coin": "BTC",
            "lado": "compra",
            "tipo": "limite",
            "cantidad": "1",
            "precio_limite": "90",
        },
    ).json()["orden"]

    assert servicio.revisar_ordenes() == []
    fuente.libros["BTC"] = libro("94", "94.5")
    [hecha] = servicio.revisar_ordenes()
    assert (hecha.orden_id, hecha.precio) == (orden["id"], D(95))

    cuenta = cliente.delete(f"/api/practica/ordenes/{segunda['id']}").json()
    assert cuenta["ordenes"] == []
    assert cuenta["reservado"] == "0"
    assert cuenta["historial"][0]["tipo"] == "limite"
    assert D(cuenta["saldo"]) == D(10000) - D(95) - D("0.01425")

    otra_vez = cliente.delete(f"/api/practica/ordenes/{segunda['id']}")
    assert otra_vez.status_code == 404
    assert otra_vez.json()["detail"].startswith("No hay ninguna orden pendiente con ese número")


def test_reiniciar(cliente: Api, fuente: FuenteFalsa) -> None:
    cliente.post(
        "/api/practica/ordenes",
        json={"coin": "BTC", "lado": "compra", "tipo": "mercado", "cantidad": "1"},
    )
    cuenta = cliente.post("/api/practica/reiniciar", json={"inicial": "25000"}).json()
    assert (cuenta["inicial"], cuenta["saldo"], cuenta["posiciones"], cuenta["historial"]) == (
        "25000",
        "25000",
        [],
        [],
    )
    assert len(list(Path("practica/anteriores").iterdir())) == 1
    por_defecto = cliente.post("/api/practica/reiniciar", json={}).json()
    assert por_defecto["inicial"] == "10000"
    assert cliente.post("/api/practica/reiniciar", json={"inicial": "0"}).status_code == 422


def test_sin_precio_no_se_inventa_el_valor(cliente: Api, fuente: FuenteFalsa) -> None:
    cliente.post(
        "/api/practica/ordenes",
        json={"coin": "BTC", "lado": "compra", "tipo": "mercado", "cantidad": "1"},
    )
    fuente.libros.clear()
    cuenta = cliente.get("/api/practica").json()
    assert cuenta["valor_total"] is None
    assert cuenta["ganancia"] is None
    [posicion] = cuenta["posiciones"]
    assert (posicion["precio"], posicion["valor"], posicion["ganancia"]) == (None, None, None)

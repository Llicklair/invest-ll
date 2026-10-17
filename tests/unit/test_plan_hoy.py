"""Qué toca hoy: las órdenes de cripto y la lista de la compra de bolsa (docs/panel-v2.md, 7).

El cálculo es puro (`plan.hoy.calcular`): aquí se le dan el plan, la cartera, los pesos que la
estrategia quiere y los precios, y se comprueba cada regla por separado.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from invest_ll.estrategias.catalogo import Ficha, ficha
from invest_ll.plan import calendario
from invest_ll.plan.hoy import (
    AVISO_USDT,
    Entrada,
    ParteDeHoy,
    Precio,
    calcular,
    compras_del_plan,
    id_de_accion,
)
from invest_ll.portfolio.models import Activity, ActivityType

D = Decimal
HOY = date(2026, 10, 17)
CREADO = date(2026, 10, 17)
FECHA_PRECIOS = date(2026, 10, 16)


def _ficha(clave: str) -> Ficha:
    encontrada = ficha(clave)
    assert encontrada is not None
    return encontrada


def _cripto(
    pesos: dict[str, float],
    precios: dict[str, str],
    *,
    clave: str = "btc-freno",
    inicial: str = "600",
    mensual: str = "20",
) -> ParteDeHoy:
    return ParteDeHoy(
        ficha=_ficha(clave),
        inicial=D(inicial),
        mensual=D(mensual),
        objetivo=pesos,
        precios={k: Precio(D(v), FECHA_PRECIOS) for k, v in precios.items()},
    )


def _bolsa(pesos: dict[str, float], *, inicial: str = "5400", mensual: str = "180") -> ParteDeHoy:
    return ParteDeHoy(
        ficha=_ficha("bolsa-equilibrada"),
        inicial=D(inicial),
        mensual=D(mensual),
        objetivo=pesos,
        precios={k: Precio(D("100"), FECHA_PRECIOS) for k in pesos},
    )


def _compra(
    simbolo: str, cantidad: str, precio: str, cuando: date, fuente: str = "plan"
) -> Activity:
    return Activity(
        timestamp=datetime(cuando.year, cuando.month, cuando.day, tzinfo=UTC),
        type=ActivityType.BUY,
        symbol=simbolo,
        quantity=D(cantidad),
        unit_price=D(precio),
        fee=D("0.1"),
        source=fuente,
    )


def _entrada(**cambios: object) -> Entrada:
    base: dict[str, object] = {
        "hoy": HOY,
        "creado": CREADO,
        "dia": 1,
        "actividades": (),
        "posiciones": {},
    }
    base.update(cambios)
    return Entrada(**base)  # type: ignore[arg-type]


# -- Calendario -------------------------------------------------------------------------------


def test_cuenta_la_aportacion_del_mes_de_creacion_aunque_su_dia_ya_pasara() -> None:
    assert calendario.vencidas(date(2026, 10, 17), 1, date(2026, 10, 17)) == 1
    assert calendario.vencidas(date(2026, 10, 17), 20, date(2026, 10, 17)) == 0
    assert calendario.vencidas(date(2026, 10, 17), 20, date(2026, 10, 20)) == 1
    assert calendario.vencidas(date(2026, 10, 17), 1, date(2027, 1, 1)) == 4


def test_proxima_y_periodo_actual() -> None:
    assert calendario.proxima(date(2026, 10, 17), 1, date(2026, 10, 17)) == date(2026, 11, 1)
    assert calendario.proxima(date(2026, 12, 5), 3, date(2026, 12, 5)) == date(2027, 1, 3)
    assert calendario.periodo_actual(date(2026, 10, 17), 20, date(2026, 10, 19)) is None
    assert calendario.periodo_actual(date(2026, 10, 17), 1, date(2026, 11, 15)) == date(2026, 11, 1)


# -- Cripto -----------------------------------------------------------------------------------


def test_plan_recien_creado_compra_inicial_mas_mensual_vencida() -> None:
    r = calcular(_entrada(cripto=_cripto({"BTC": 1.0}, {"BTC": "62000"})))

    (accion,) = r.acciones
    assert accion.donde == "binance"
    assert accion.par == "BTC/USDT"
    assert accion.lado == "buy"
    # 600 + 20 x 1 vencida = 620 USDT a 62.000 = 0,01 BTC
    assert accion.cantidad == D("0.010000")
    assert accion.importe == D("620.00")
    assert accion.moneda == "USDT"
    assert accion.precio_fecha == FECHA_PRECIOS
    assert "Bitcoin vale más que hace 30 días" in accion.explicacion
    assert AVISO_USDT in r.avisos


def test_cantidades_redondeadas_hacia_abajo_a_seis_decimales() -> None:
    r = calcular(_entrada(cripto=_cripto({"BTC": 1.0}, {"BTC": "81615.64"})))
    (accion,) = r.acciones
    assert accion.cantidad == D("0.007596")  # 620 / 81615.64 = 0.0075965...
    assert accion.cantidad is not None and accion.cantidad * D("81615.64") <= D(620)


def test_sin_aportaciones_vencidas_no_hay_nada_que_comprar() -> None:
    r = calcular(_entrada(dia=20, cripto=_cripto({"BTC": 1.0}, {"BTC": "60000"})))
    assert r.acciones == ()
    assert r.proxima_fecha == date(2026, 10, 20)
    assert r.resumen == "No toca hacer nada. Tu próxima aportación es el 20 de octubre."


def test_diferencias_de_10_usdt_o_menos_no_dan_orden() -> None:
    compra = _compra("BTC/USDT", "0.0101", "60000", CREADO, "ledger:pruebas")  # 606 + 0,1 pagado
    r = calcular(
        _entrada(
            actividades=[compra],
            posiciones={"BTC/USDT": D("0.0101")},
            cripto=_cripto({"BTC": 1.0}, {"BTC": "60000"}),
        )
    )
    # Le tocan 620; pagó 606,10, así que quedan 13,90 en USDT: 606 + 13,90 = 619,90 de parte,
    # todo debería estar en BTC y le faltan 13,90 > 10 -> una compra pequeña.
    (accion,) = r.acciones
    assert accion.importe == pytest.approx(D("13.86"), abs=D("0.1"))

    sin_hueco = calcular(
        _entrada(
            actividades=[_compra("BTC/USDT", "0.0102", "60000", CREADO, "ledger:pruebas")],
            posiciones={"BTC/USDT": D("0.0102")},
            cripto=_cripto({"BTC": 1.0}, {"BTC": "60000"}),
        )
    )
    assert sin_hueco.acciones == (), "le faltan 7,90 USDT: por debajo del umbral de 10"


def test_si_la_estrategia_sale_se_vende_todo_y_las_ventas_van_primero() -> None:
    r = calcular(
        _entrada(
            actividades=[
                _compra("BTC/USDT", "0.01", "50000", CREADO, "ledger:pruebas"),
                _compra("ETH/USDT", "0.04", "2500", CREADO, "ledger:pruebas"),
            ],
            posiciones={"BTC/USDT": D("0.01"), "ETH/USDT": D("0.04")},
            cripto=_cripto(
                {"ETH": 1.0}, {"BTC": "60000", "ETH": "3000"}, clave="cripto-cesta-freno"
            ),
        )
    )
    lados = [(a.par, a.lado) for a in r.acciones]
    assert lados[0] == ("BTC/USDT", "sell")
    assert r.acciones[0].cantidad == D("0.010000"), "salir del todo vende lo que hay"
    assert ("ETH/USDT", "buy") in lados
    assert "ya no está entre las elegidas" in r.acciones[0].explicacion.lower()


def test_la_parte_crece_con_el_mercado_y_no_se_vende_la_subida() -> None:
    """Si BTC se dobla, la parte vale el doble: no hay orden para volver a lo aportado."""
    r = calcular(
        _entrada(
            actividades=[_compra("BTC/USDT", "0.0124", "50000", CREADO, "ledger:pruebas")],
            posiciones={"BTC/USDT": D("0.0124")},
            cripto=_cripto({"BTC": 1.0}, {"BTC": "100000"}),
        )
    )
    assert r.acciones == ()


def test_la_banda_de_no_operar_de_la_cesta() -> None:
    # Con 10.000 en la parte, un 1 % de diferencia son 100 USDT (> 10) pero menos que la banda.
    parte = _cripto(
        {"BTC": 0.51}, {"BTC": "100"}, clave="cripto-cesta-freno", inicial="10000", mensual="0"
    )
    r = calcular(
        _entrada(
            actividades=[_compra("BTC/USDT", "50", "100", CREADO, "ledger:pruebas")],
            posiciones={"BTC/USDT": D("50")},
            cripto=parte,
        )
    )
    assert r.acciones == ()


def test_sin_precio_no_se_inventa_la_orden() -> None:
    r = calcular(
        _entrada(
            posiciones={"FOO/USDT": D("3")},
            actividades=[_compra("FOO/USDT", "3", "10", CREADO, "ledger:pruebas")],
            cripto=_cripto({"BTC": 1.0}, {"BTC": "60000"}),
        )
    )
    assert r.acciones == ()
    assert any("falta el precio de FOO" in a for a in r.avisos)


def test_con_las_compras_en_pausa_solo_ventas() -> None:
    r = calcular(_entrada(pausa="motivo X", cripto=_cripto({"BTC": 1.0}, {"BTC": "60000"})))
    assert r.acciones == ()
    assert any("pausa" in a and "motivo X" in a for a in r.avisos)


def test_ids_estables_el_mismo_dia_y_distintos_otro_dia() -> None:
    parte = _cripto({"BTC": 1.0}, {"BTC": "60000"})
    a = calcular(_entrada(cripto=parte)).acciones[0].id
    b = calcular(_entrada(cripto=parte)).acciones[0].id
    otro = calcular(_entrada(cripto=parte, hoy=date(2026, 10, 18))).acciones[0].id
    assert a == b == id_de_accion(HOY, "binance", "btc-freno", "BTC/USDT", "buy")
    assert otro != a


# -- Bolsa ------------------------------------------------------------------------------------


def test_la_primera_vez_inicial_mas_mensual_por_el_peso_de_cada_fondo() -> None:
    r = calcular(_entrada(bolsa=_bolsa({"SPY": 0.6, "IEF": 0.4})))

    spy, ief = r.acciones
    assert (spy.simbolo, spy.importe) == ("SPY", D("3348.00"))  # (5400 + 180) x 0,6
    assert (ief.simbolo, ief.importe) == ("IEF", D("2232.00"))
    assert spy.donde == "broker" and spy.par is None and spy.moneda == "EUR"
    assert spy.cantidad == D("33.4800")  # aproximada: importe / último cierre
    assert spy.equivalente is not None and "IE00B5BMR087" in spy.equivalente
    assert spy.titulo == "Compra unos 3.348 € de un ETF del S&P 500"
    assert "con lo que pones al empezar" in spy.explicacion
    assert r.resumen == "Hoy toca: 2 compras en tu bróker."


def test_lo_anotado_en_el_periodo_quita_su_linea_y_las_demas_no_cambian() -> None:
    hecha = _compra("SPY", "33.48", "100", HOY)
    r = calcular(_entrada(actividades=[hecha], bolsa=_bolsa({"SPY": 0.6, "IEF": 0.4})))
    (ief,) = r.acciones
    assert (ief.simbolo, ief.importe) == ("IEF", D("2232.00")), "sigue incluyendo el inicial"


def test_el_mes_siguiente_solo_la_mensual() -> None:
    hechas = [_compra("SPY", "33.48", "100", HOY), _compra("IEF", "22.32", "100", HOY)]
    noviembre = date(2026, 11, 2)
    r = calcular(
        _entrada(hoy=noviembre, actividades=hechas, bolsa=_bolsa({"SPY": 0.6, "IEF": 0.4}))
    )
    assert [(a.simbolo, a.importe) for a in r.acciones] == [
        ("SPY", D("108.00")),
        ("IEF", D("72.00")),
    ]
    assert all(a.periodo == date(2026, 11, 1) for a in r.acciones)


def test_solo_cuentan_las_compras_anotadas_con_el_plan() -> None:
    a_mano = _compra("SPY", "1", "100", HOY, fuente="panel")
    assert compras_del_plan([a_mano], ["SPY"], CREADO) == []
    r = calcular(_entrada(actividades=[a_mano], bolsa=_bolsa({"SPY": 1.0})))
    assert len(r.acciones) == 1


def test_bolsa_con_compras_en_pausa_no_propone_nada() -> None:
    r = calcular(_entrada(pausa="motivo Y", bolsa=_bolsa({"SPY": 1.0})))
    assert r.acciones == ()
    assert any("motivo Y" in a for a in r.avisos)


def test_la_pausa_se_dice_una_vez_y_sin_parentesis_dentro_de_parentesis() -> None:
    """Salía dos veces y como "en pausa (motivo (desde 2026-10-17)): ..."."""
    r = calcular(
        _entrada(
            pausa="motivo Z (desde el 17 oct 2026)",
            cripto=_cripto({"BTC": 1.0}, {"BTC": "60000"}),
            bolsa=_bolsa({"SPY": 1.0}),
        )
    )
    de_pausa = [a for a in r.avisos if "pausa" in a]
    assert len(de_pausa) == 1
    assert de_pausa[0].startswith("Las compras están en pausa: motivo Z (desde el 17 oct 2026).")
    assert "))" not in de_pausa[0]


def test_resumen_con_las_dos_partes() -> None:
    r = calcular(
        _entrada(
            cripto=_cripto({"BTC": 1.0}, {"BTC": "60000"}), bolsa=_bolsa({"SPY": 0.6, "IEF": 0.4})
        )
    )
    assert r.resumen == "Hoy toca: 1 orden en Binance y 2 compras en tu bróker."

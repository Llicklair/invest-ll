"""Qué toca hoy: las órdenes de cripto y la lista de la compra de bolsa (docs/panel-v2.md, 7).

El cálculo es puro (`plan.hoy.calcular`): aquí se le dan el plan, la cartera, los pesos que la
estrategia quiere y los precios, y se comprueba cada regla por separado.
"""

from __future__ import annotations

from dataclasses import replace
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
    VentaImposibleError,
    calcular,
    compras_del_plan,
    en_el_broker,
    id_de_accion,
    venta_en_unidades,
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


def test_lo_anotado_cuenta_desde_la_primera_aportacion_aunque_sea_antes_de_crear_el_plan() -> None:
    """Creado el 17 con día 1, `hecho` acepta la compra de la aportación de octubre con fecha 5:
    antes se aceptaba pero no contaba, y la línea seguía pendiente (invitaba a comprar dos veces)."""
    assert calendario.inicio(date(2026, 10, 17), 1) == date(2026, 10, 1)
    assert calendario.inicio(date(2026, 10, 17), 20) == date(2026, 10, 17)
    hecha = _compra("SPY", "33.48", "100", date(2026, 10, 5))
    r = calcular(_entrada(actividades=[hecha], bolsa=_bolsa({"SPY": 0.6, "IEF": 0.4})))
    assert [(a.simbolo, a.importe) for a in r.acciones] == [("IEF", D("2232.00"))]


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


# -- Bolsa: ventas en el bróker ---------------------------------------------------------------
#
# Un plan creado el 1 de octubre que ya compró su aportación ese día (así no hay líneas de
# aportación pendientes y se ve solo lo que sobra). Todo a 100 para que las cuentas se lean.

OCTUBRE = date(2026, 10, 1)


def _parte_bolsa(
    clave: str, pesos: dict[str, float], precios: dict[str, str] | None = None
) -> ParteDeHoy:
    return ParteDeHoy(
        ficha=_ficha(clave),
        inicial=D("10000"),
        mensual=D("0"),
        objetivo=pesos,
        precios={
            k: Precio(D(v), FECHA_PRECIOS)
            for k, v in (
                precios or dict.fromkeys(("SPY", "IEF", "EEM", "SHY", "GLD"), "100")
            ).items()
        },
    )


def _movimiento(
    tipo: ActivityType, simbolo: str, cantidad: str, cuando: date, fuente: str = "plan"
) -> Activity:
    return Activity(
        timestamp=datetime(cuando.year, cuando.month, cuando.day, tzinfo=UTC),
        type=tipo,
        symbol=simbolo,
        quantity=D(cantidad),
        unit_price=D("100"),
        source=fuente,
    )


def _con_cartera(
    parte: ParteDeHoy,
    tienes: dict[str, str],
    *,
    despues: tuple[Activity, ...] | list[Activity] = (),
    **cambios: object,
) -> Entrada:
    """El plan compró `tienes` el 1 de octubre; hoy es el 17 y la estrategia quiere `parte`."""
    compras = [_movimiento(ActivityType.BUY, s, q, OCTUBRE) for s, q in tienes.items()]
    actividades = [*compras, *despues]
    posiciones: dict[str, Decimal] = {}
    for a in actividades:
        assert a.symbol is not None
        signo = 1 if a.type is ActivityType.BUY else -1
        posiciones[a.symbol] = posiciones.get(a.symbol, D(0)) + signo * a.quantity
    base: dict[str, object] = {
        "creado": OCTUBRE,
        "actividades": actividades,
        "posiciones": {s: q for s, q in posiciones.items() if q > 0},
        "bolsa": parte,
    }
    base.update(cambios)
    return _entrada(**base)


def test_prudente_sale_de_un_fondo_que_baja_y_lo_liberado_va_a_la_lista_de_la_compra() -> None:
    parte = _parte_bolsa("bolsa-prudente", {"SPY": 0.5, "SHY": 0.5})
    r = calcular(_con_cartera(parte, {"SPY": "40", "SHY": "40", "EEM": "20"}))

    venta, *compras = r.acciones
    assert (venta.donde, venta.simbolo, venta.lado) == ("broker", "EEM", "sell")
    assert venta.importe == D("2000.00"), "su objetivo es 0: se vende entero"
    assert venta.cantidad == D("20.0000")
    assert venta.todo is True
    assert venta.titulo == "Vende todo tu ETF de mercados emergentes (unos 2.000 €)"
    assert venta.explicacion.startswith("Lleva meses bajando: tu estrategia sale de él")
    assert "Es el 20 % de tu parte de bolsa" in venta.explicacion
    assert "lo que saques va a la lista de la compra" in venta.explicacion
    assert (venta.moneda, venta.referencia, venta.precio_ref_moneda) == ("EUR", "EEM", "USD")
    assert venta.periodo is None
    assert venta.id == id_de_accion(HOY, "broker", "bolsa-prudente", "EEM", "sell")
    # Lo liberado, a lo que queda por debajo de su objetivo: 40 % -> 50 % cada uno.
    assert [(c.simbolo, c.lado, c.importe) for c in compras] == [
        ("SHY", "buy", D("1000.00")),
        ("SPY", "buy", D("1000.00")),
    ]
    assert compras[1].explicacion == (
        "Con lo que sacas al vender: tu estrategia quiere un 50 % de tu parte de bolsa en "
        "Bolsa de EE.UU. y ahora tiene un 40 %."
    )
    assert compras[1].periodo is None, "no es de la aportación: no tiene fecha mínima"
    assert r.resumen == "Hoy toca: 1 venta y 2 compras en tu bróker."


def test_un_fondo_que_sale_pero_pesa_menos_que_el_umbral_no_se_vende() -> None:
    """Un 5 % fuera de su objetivo no llega al 10 %: lo absorben las aportaciones."""
    parte = _parte_bolsa("bolsa-prudente", {"SPY": 0.5, "SHY": 0.5})
    r = calcular(_con_cartera(parte, {"SPY": "47.5", "SHY": "47.5", "EEM": "5"}))
    assert r.acciones == ()


def test_una_reduccion_que_no_llega_a_cero_vende_solo_lo_que_sobra() -> None:
    parte = _parte_bolsa("bolsa-prudente", {"SPY": 0.3, "GLD": 0.1, "SHY": 0.6})
    r = calcular(_con_cartera(parte, {"SPY": "45", "GLD": "10", "SHY": "45"}))

    venta, compra = r.acciones
    assert (venta.simbolo, venta.lado, venta.importe, venta.todo) == (
        "SPY",
        "sell",
        D("1500.00"),
        False,
    )
    assert venta.cantidad == D("15.0000")
    assert venta.titulo == "Vende unos 1.500 € de un ETF del S&P 500"
    assert venta.explicacion == (
        "Pesa el 45 % de tu parte de bolsa y tu estrategia quiere un 30 %: vende lo que sobra; "
        "lo que saques va a la lista de la compra."
    )
    assert (compra.simbolo, compra.lado, compra.importe) == ("SHY", "buy", D("1500.00"))


def test_las_ventas_tienen_en_cuenta_la_aportacion_que_aun_no_se_ha_comprado() -> None:
    """A mitad de comprar el inicial (SPY sí, IEF aún no), SPY no "sobra": falta comprar IEF."""
    hecha = _compra("SPY", "33.48", "100", HOY)
    r = calcular(
        _entrada(
            actividades=[hecha],
            posiciones={"SPY": D("33.48")},
            bolsa=_bolsa({"SPY": 0.6, "IEF": 0.4}),
        )
    )
    (ief,) = r.acciones
    assert (ief.simbolo, ief.lado, ief.importe) == ("IEF", "buy", D("2232.00"))


@pytest.mark.parametrize(
    ("spy", "ief", "vende"),
    [
        ("65", "35", None),  # el reparto se ha movido 5 puntos: nada
        ("69", "31", None),  # 9 puntos: todavía nada
        ("75", "25", D("1500.00")),  # 15 puntos: deriva extrema, se vende lo que sobra
    ],
)
def test_equilibrada_solo_vende_con_una_deriva_extrema(
    spy: str, ief: str, vende: Decimal | None
) -> None:
    parte = _parte_bolsa("bolsa-equilibrada", {"SPY": 0.6, "IEF": 0.4})
    r = calcular(_con_cartera(parte, {"SPY": spy, "IEF": ief}))
    ventas = [a for a in r.acciones if a.lado == "sell"]
    if vende is None:
        assert r.acciones == ()
    else:
        (venta,) = ventas
        assert (venta.simbolo, venta.importe) == ("SPY", vende)
        assert [(a.simbolo, a.importe) for a in r.acciones if a.lado == "buy"] == [
            ("IEF", D("1500.00"))
        ]


def test_bolsa_de_eeuu_no_vende_nunca() -> None:
    """Un solo fondo al 100 %: nunca pesa más de lo que quiere la estrategia, suba lo que suba."""
    parte = _parte_bolsa("bolsa-eeuu", {"SPY": 1.0}, {"SPY": "300"})
    r = calcular(_con_cartera(parte, {"SPY": "100"}))
    assert r.acciones == ()


def test_solo_se_vende_lo_que_compro_el_plan() -> None:
    """Lo que tuvieras antes del plan (o anotado a mano) no es de la estrategia: no se toca."""
    parte = _parte_bolsa("bolsa-prudente", {"SPY": 0.5, "SHY": 0.5})
    a_mano = _movimiento(ActivityType.BUY, "EEM", "50", OCTUBRE, fuente="panel")
    r = calcular(_con_cartera(parte, {"SPY": "50", "SHY": "50"}, despues=[a_mano]))
    assert r.acciones == ()


def test_lo_cobrado_y_no_reinvertido_sigue_en_la_lista_de_la_compra() -> None:
    parte = _parte_bolsa("bolsa-prudente", {"SPY": 0.5, "SHY": 0.5})
    vendida = _movimiento(ActivityType.SELL, "EEM", "20", HOY)
    r = calcular(_con_cartera(parte, {"SPY": "40", "SHY": "40", "EEM": "20"}, despues=[vendida]))

    assert [(a.simbolo, a.lado, a.importe) for a in r.acciones] == [
        ("SHY", "buy", D("1000.00")),
        ("SPY", "buy", D("1000.00")),
    ]
    assert r.acciones[0].explicacion.startswith(
        "Con lo que cobraste al vender y aún no has invertido:"
    )

    # Comprar con ese dinero lo gasta: lo que queda va al otro fondo.
    spy = _movimiento(ActivityType.BUY, "SPY", "10", HOY)
    r = calcular(
        _con_cartera(parte, {"SPY": "40", "SHY": "40", "EEM": "20"}, despues=[vendida, spy])
    )
    assert [(a.simbolo, a.importe) for a in r.acciones] == [("SHY", D("1000.00"))]


def test_lo_liberado_se_suma_a_la_linea_de_la_aportacion() -> None:
    parte = replace(_parte_bolsa("bolsa-prudente", {"SPY": 0.5, "SHY": 0.5}), mensual=D("200"))
    # El 1 de noviembre toca la aportación (200 €, 100 a cada uno) y EEM ha salido.
    r = calcular(
        _con_cartera(parte, {"SPY": "40", "SHY": "40", "EEM": "20"}, hoy=date(2026, 11, 2))
    )
    venta, shy, spy = r.acciones
    assert venta.importe == D("2000.00")
    assert (spy.simbolo, spy.importe) == ("SPY", D("1100.00"))
    assert spy.periodo == date(2026, 11, 1)
    assert spy.explicacion == (
        "Tu aportación de noviembre (200 €): el 50 % va a Bolsa de EE.UU., según el reparto de "
        "Prudente con freno; y unos 1.000 € de lo que sacas al vender."
    )
    assert shy.importe == D("1100.00")


def test_si_el_objetivo_deja_liquidez_lo_liberado_se_queda_y_se_dice() -> None:
    parte = _parte_bolsa("bolsa-prudente", {"SPY": 0.5})  # la otra mitad, en liquidez
    r = calcular(_con_cartera(parte, {"SPY": "50", "EEM": "50"}))
    (venta,) = r.acciones
    assert venta.explicacion.endswith(
        "lo que saques se queda sin invertir en tu bróker: tu estrategia lo quiere en liquidez "
        "por ahora."
    )

    mixto = calcular(_con_cartera(parte, {"SPY": "30", "EEM": "70"}))
    venta, spy = mixto.acciones
    assert spy.importe == D("2000.00"), "SPY va del 30 % al 50 %"
    assert "unos 5.000 € se quedan sin invertir en tu bróker" in venta.explicacion


def test_con_las_compras_en_pausa_se_vende_y_no_se_compra() -> None:
    parte = _parte_bolsa("bolsa-prudente", {"SPY": 0.5, "SHY": 0.5})
    r = calcular(_con_cartera(parte, {"SPY": "40", "SHY": "40", "EEM": "20"}, pausa="motivo W"))
    (venta,) = r.acciones
    assert venta.lado == "sell"
    assert "con las compras en pausa, lo que saques se queda sin invertir" in venta.explicacion


def test_sin_precio_de_un_fondo_que_tienes_no_se_inventa_la_venta() -> None:
    parte = _parte_bolsa("bolsa-prudente", {"SPY": 0.5, "SHY": 0.5}, {"SPY": "100", "SHY": "100"})
    r = calcular(_con_cartera(parte, {"SPY": "40", "SHY": "40", "EEM": "20"}))
    assert r.acciones == ()
    assert any("falta el precio de" in a and "vender" in a for a in r.avisos)


def test_con_el_registro_ilegible_no_se_proponen_ventas() -> None:
    parte = _parte_bolsa("bolsa-prudente", {"SPY": 0.5, "SHY": 0.5})
    r = calcular(_con_cartera(parte, {"SPY": "40", "SHY": "40", "EEM": "20"}, broker_legible=False))
    assert r.acciones == ()


def test_resumen_con_ventas_y_compras_en_el_broker_y_ordenes_en_binance() -> None:
    parte = _parte_bolsa("bolsa-prudente", {"SPY": 0.5, "SHY": 0.5})
    r = calcular(
        _con_cartera(
            parte,
            {"SPY": "40", "SHY": "40", "EEM": "20"},
            cripto=_cripto({"BTC": 1.0}, {"BTC": "60000"}),
        )
    )
    assert r.resumen == "Hoy toca: 1 orden en Binance; 1 venta y 2 compras en tu bróker."


# -- Lo que el plan tiene en el bróker y cómo se anota una venta --------------------------------


def test_en_el_broker_cuenta_solo_lo_del_plan_y_las_ventas_del_dia_van_primero() -> None:
    actividades = [
        _movimiento(ActivityType.BUY, "EEM", "20", OCTUBRE),
        _movimiento(ActivityType.BUY, "EEM", "5", OCTUBRE, fuente="panel"),
        _movimiento(ActivityType.BUY, "SHY", "10", HOY),  # anotada antes que la venta del día
        _movimiento(ActivityType.SELL, "EEM", "20", HOY),
    ]
    tenido = en_el_broker(actividades, OCTUBRE, {"EEM": D("5"), "SHY": D("10")})
    assert tenido.unidades == {"SHY": D("10")}, "las 5 de EEM a mano no son del plan"
    assert tenido.libre == D("1000"), "la venta de 2.000 pagó la compra de 1.000 del mismo día"

    antes = en_el_broker(actividades, OCTUBRE, {"EEM": D("25")}, hasta=date(2026, 10, 16))
    assert antes.unidades == {"EEM": D("20")}
    assert antes.libre == 0


def test_lo_vendido_a_mano_tampoco_se_vende_dos_veces() -> None:
    """Si vendiste a mano parte de lo del plan, lo del plan no pasa de lo que tienes."""
    tenido = en_el_broker(
        [_movimiento(ActivityType.BUY, "EEM", "20", OCTUBRE)], OCTUBRE, {"EEM": D("8")}
    )
    assert tenido.unidades == {"EEM": D("8")}


def test_venta_en_unidades_parcial_al_precio_de_referencia() -> None:
    v = venta_en_unidades(D("300"), D("100"), D("10"), sale_del_todo=False, nombre="Oro")
    assert (v.unidades, v.precio, v.todo) == (D("3"), D("100"), False)


def test_venta_en_unidades_sin_pasar_de_lo_que_tienes() -> None:
    """El euro se ha movido: cobraste un 10 % más de lo que valen tus unidades en dólares."""
    v = venta_en_unidades(D("1100"), D("100"), D("10"), sale_del_todo=False, nombre="Oro")
    assert (v.unidades, v.todo) == (D("10"), True)
    assert v.unidades * v.precio == D("1100"), "lo cobrado, exacto"


def test_venta_en_unidades_saliendo_del_todo_no_deja_restos() -> None:
    v = venta_en_unidades(D("900"), D("100"), D("10"), sale_del_todo=True, nombre="Oro")
    assert (v.unidades, v.todo) == (D("10"), True)
    v = venta_en_unidades(D("500"), D("100"), D("10"), sale_del_todo=True, nombre="Oro")
    assert (v.unidades, v.todo) == (D("5"), False), "la mitad: vendiste solo una parte"


@pytest.mark.parametrize(("cobrado", "tienes"), [("1300", "10"), ("100", "0")])
def test_venta_en_unidades_imposible(cobrado: str, tienes: str) -> None:
    with pytest.raises(VentaImposibleError, match="Oro"):
        venta_en_unidades(D(cobrado), D("100"), D(tienes), sale_del_todo=False, nombre="Oro")

"""Los nombres llanos (un único sitio) y las cifras a la española."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from invest_ll import llano, nombres
from invest_ll.fetch import available


@pytest.mark.parametrize(
    "simbolo", ["BTC/USDT", "BTCUSDT", "btc-usdt", "BTCUSDT~2", " BTC/USDT ", "BTC"]
)
def test_todas_las_formas_de_bitcoin_se_llaman_bitcoin(simbolo: str) -> None:
    assert nombres.base(simbolo) == "BTC"
    assert nombres.nombre_llano(simbolo) == "Bitcoin"


@pytest.mark.parametrize(
    ("simbolo", "nombre"),
    [
        ("SPY", "Bolsa de EE.UU."),
        ("GLD", "Oro"),
        ("IEF", "Bonos del Tesoro de EE.UU. a 7-10 años"),
        ("SHY", "Bonos del Tesoro de EE.UU. a corto plazo"),
    ],
)
def test_los_fondos_tienen_nombre_llano(simbolo: str, nombre: str) -> None:
    assert nombres.nombre_llano(simbolo) == nombre


def test_lo_desconocido_se_queda_con_su_nombre_sin_la_moneda() -> None:
    assert nombres.nombre_llano("FOOUSDT") == "FOO"
    assert nombres.nombre_conocido("FOOUSDT") is None


@pytest.mark.parametrize(
    ("simbolo", "cripto"),
    [("BTC/USDT", True), ("ETHUSDT", True), ("BTC-USDT", True), ("SPY", False), ("GLD", False)],
)
def test_que_es_cripto(simbolo: str, cripto: bool) -> None:
    assert nombres.es_cripto(simbolo) is cripto


def test_isin_solo_donde_la_especificacion_lo_da() -> None:
    """docs/panel-v2.md, 5: ISIN solo para SPY, GLD y EEM; el resto, la categoría en llano."""
    con_isin = {s for s in ("SPY", "IEF", "GLD", "EEM", "EFA", "TLT", "DBC", "VNQ", "SHY")
                if "ISIN" in (nombres.equivalente(s) or "")}  # fmt: skip
    assert con_isin == {"SPY", "GLD", "EEM"}
    assert "IE00B5BMR087" in (nombres.equivalente("SPY") or "")
    assert "IE00B4ND3602" in (nombres.equivalente("GLD") or "")
    assert "IE00BKM4GZ66" in (nombres.equivalente("EEM") or "")
    assert nombres.equivalente("BTC/USDT") is None


def test_el_mercado_del_panel_anterior_usa_los_mismos_nombres() -> None:
    """Un único sitio: la columna "que es" del mercado sale de `invest_ll.nombres`."""
    assert available.NOMBRES is nombres.NOMBRES


def test_cifras_y_fechas_a_la_espanola() -> None:
    assert llano.numero(Decimal("1234.567")) == "1.234,57"
    assert llano.euros(Decimal(1500)) == "1.500 €"
    assert llano.euros(Decimal("12.5")) == "12,50 €"
    assert llano.porcentaje(0.57) == "57 %"
    assert llano.fecha_corta(date(2026, 10, 15)) == "15 oct 2026"
    assert llano.fecha_larga(date(2026, 11, 1)) == "1 de noviembre"


@pytest.mark.parametrize(
    ("simbolo", "moneda"),
    [
        ("BTC/USDT", "USDT"),
        ("BTCUSDT", "USDT"),
        ("btc-usdt", "USDT"),
        ("LUNAUSDT~2", "USDT"),
        ("BTC/EUR", "EUR"),
        ("SPY", "USD"),
        ("SAN.MC", "EUR"),
    ],
)
def test_la_moneda_en_que_cotiza(simbolo: str, moneda: str) -> None:
    assert nombres.moneda_de(simbolo) == moneda


def test_cantidades_y_dinero_a_la_espanola() -> None:
    assert llano.cantidad(Decimal("0.00122")) == "0,00122"
    assert llano.cantidad(Decimal("5.4370")) == "5,437"
    assert llano.cantidad(Decimal(1500)) == "1.500"
    assert llano.dinero(Decimal("82245.93"), "USDT") == "82.245,93 USDT"
    assert llano.dinero(Decimal("763.25"), "USD") == "763,25 $"
    assert llano.dinero(Decimal(650), "EUR") == "650 €"
    assert llano.dinero(Decimal("0.0000123"), "USDT") == "0,0000123 USDT", "nunca 0,00"

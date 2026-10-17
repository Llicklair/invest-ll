"""Las fichas de los exchanges, contrastadas con lo que dice ccxt (sin red: solo se construye el
objeto, que no habla con nadie hasta que se le pide algo).

Si ccxt cambia lo que pide un exchange (otro campo de las claves, otra red de pruebas), esto falla
aquí en vez de en la cara de Marcos al pegar las claves.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import ccxt
import pytest

from invest_ll.exchanges.ccxt_conector import ConectorCcxt
from invest_ll.exchanges.conector import ExchangeError
from invest_ll.exchanges.fichas import FICHAS, POR_ID, Ficha
from invest_ll.exchanges.red_ccxt import RedEquivocadaError, apunta_a_pruebas, construir

IDS = [f.id for f in FICHAS]


def _ccxt(ficha: Ficha) -> Any:
    return getattr(ccxt, ficha.id_ccxt)()


def test_los_seis_exchanges_de_la_decision_de_marcos() -> None:
    assert IDS == [
        "binance",
        "hyperliquid",
        "bybit",
        "okx",
        "kraken",
        "coinbase",
    ]
    assert set(POR_ID) == set(IDS)


@pytest.mark.parametrize("ficha", FICHAS, ids=IDS)
def test_los_campos_son_los_que_pide_ccxt(ficha: Ficha) -> None:
    pide = {k for k, v in _ccxt(ficha).requiredCredentials.items() if v}
    assert {c.clave for c in ficha.campos} == pide


@pytest.mark.parametrize("ficha", FICHAS, ids=IDS)
def test_tiene_red_de_pruebas_si_ccxt_la_tiene(ficha: Ficha) -> None:
    assert ficha.tiene_pruebas == (_ccxt(ficha).urls.get("test") is not None)


@pytest.mark.parametrize("ficha", FICHAS, ids=IDS)
def test_cada_ficha_se_explica_en_llano(ficha: Ficha) -> None:
    assert ficha.como_conseguir_real
    assert any(
        "retir" in paso.lower() or "transfer" in paso.lower() for paso in ficha.como_conseguir_real
    )
    assert bool(ficha.como_conseguir_pruebas) == ficha.tiene_pruebas
    if not ficha.tiene_pruebas:
        assert ficha.aviso is not None
        assert "ficticio" in ficha.aviso
    for campo in ficha.campos:
        assert campo.nombre
        assert campo.ayuda


@pytest.mark.parametrize("ficha", FICHAS, ids=IDS)
def test_los_permisos_se_piden_con_metodos_que_ccxt_tiene(ficha: Ficha) -> None:
    metodos = {
        "binance": "sapiGetAccountApiRestrictions",
        "bybit": "privateGetV5UserQueryApi",
        "okx": "privateGetAccountConfig",
        "kraken": "privatePostGetApiKeyInfo",
        "coinbase": "v3PrivateGetBrokerageKeyPermissions",
        "hyperliquid": "publicPostInfo",
    }
    assert callable(getattr(_ccxt(ficha), metodos[ficha.permisos]))


@pytest.mark.parametrize("ficha", FICHAS, ids=IDS)
def test_las_velas_por_peticion_y_el_par_de_referencia(ficha: Ficha) -> None:
    assert ficha.max_velas > 0
    assert "/" in ficha.par_de_referencia


@pytest.mark.parametrize("ficha", [f for f in FICHAS if f.tiene_pruebas], ids=lambda f: f.id)
def test_la_red_de_pruebas_apunta_a_pruebas(ficha: Ficha) -> None:
    assert apunta_a_pruebas(ficha, construir(ficha, "pruebas", None))
    assert not apunta_a_pruebas(ficha, construir(ficha, "real", None))


def test_si_la_red_de_pruebas_no_apunta_a_pruebas_se_para(monkeypatch: pytest.MonkeyPatch) -> None:
    def nunca(ficha: Ficha, exchange: object) -> bool:
        return False

    monkeypatch.setattr("invest_ll.exchanges.red_ccxt.apunta_a_pruebas", nunca)
    with pytest.raises(RedEquivocadaError, match="no apunta a la red de pruebas"):
        construir(POR_ID["binance"], "pruebas", None)


def test_un_exchange_sin_pruebas_no_construye_pruebas() -> None:
    with pytest.raises(Exception, match="no tiene red de pruebas"):
        construir(POR_ID["kraken"], "pruebas", None)


def test_las_opciones_dejan_solo_el_contado() -> None:
    ex = construir(POR_ID["bybit"], "real", None)
    assert ex.options["defaultType"] == "spot"
    assert ex.options["fetchMarkets"]["types"] == ["spot"]


def test_las_claves_llegan_a_ccxt() -> None:
    ex = construir(POR_ID["okx"], "pruebas", {"apiKey": "k", "secret": "s", "password": "p"})
    assert (ex.apiKey, ex.secret, ex.password) == ("k", "s", "p")


def test_redondeo_y_minimos_con_el_ccxt_de_verdad_sin_red() -> None:
    """Las funciones de ccxt que usa el conector (`amount_to_precision`, `price_to_precision`),
    las de verdad, con un mercado puesto a mano: así no se habla con nadie."""
    ex = ccxt.binance()
    mercado = {
        "id": "BTCUSDT",
        "symbol": "BTC/USDT",
        "base": "BTC",
        "quote": "USDT",
        "spot": True,
        "active": True,
        "precision": {"amount": 0.00001, "price": 0.01},
        "limits": {"amount": {"min": 0.00001}, "cost": {"min": 5.0}},
        "taker": 0.001,
        "maker": 0.001,
    }
    ex.markets = {"BTC/USDT": mercado}
    ex.markets_by_id = {"BTCUSDT": [mercado]}
    ex.symbols = ["BTC/USDT"]
    c = ConectorCcxt(ex, POR_ID["binance"], "pruebas", claves={"apiKey": "k", "secret": "s"})

    assert c.mercado("BTC/USDT").paso_cantidad == Decimal("0.00001")
    lista = c._preparar(  # pyright: ignore[reportPrivateUsage]
        mercado, "BTC/USDT", "compra", Decimal("0.0012345"), "limite", Decimal("60000.129")
    )
    assert (lista.cantidad, lista.precio) == ("0.00123", "60000.13")
    with pytest.raises(ExchangeError, match="se queda en cero"):
        c._preparar(  # pyright: ignore[reportPrivateUsage]
            mercado, "BTC/USDT", "compra", Decimal("0.000001"), "limite", Decimal(60000)
        )
    with pytest.raises(ExchangeError, match="importe mínimo"):
        c._preparar(  # pyright: ignore[reportPrivateUsage]
            mercado, "BTC/USDT", "compra", Decimal("0.00005"), "limite", Decimal(60000)
        )

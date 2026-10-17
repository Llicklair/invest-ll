"""El registro: el único sitio donde se piden los conectores, y los cerrojos al pedirlos."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from invest_ll.exchanges import credenciales, registro
from invest_ll.exchanges.activacion import Comprobacion, ConfigExchanges, huella
from invest_ll.exchanges.ccxt_conector import ConectorCcxt
from invest_ll.exchanges.conector import ExchangeError
from invest_ll.exchanges.credenciales import ClavesExchange
from invest_ll.exchanges.falso import ConectorFalso
from invest_ll.exchanges.fichas import BYBIT, KRAKEN

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path

T0 = datetime(2026, 10, 17, tzinfo=UTC)
CLAVES = ClavesExchange(valores={"apiKey": "CLAVE-K-1", "secret": "SECRETO-K-1"})


@pytest.fixture(autouse=True)
def en_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def _activar_kraken_en_real() -> None:
    credenciales.guardar(KRAKEN, "real", CLAVES)
    config = ConfigExchanges()
    config.guardar_comprobacion(
        "kraken", "real", Comprobacion(T0, huella(KRAKEN, "real", CLAVES), True, False, "")
    )
    config.guardar_activo("kraken", "real", at=T0)


def test_los_disponibles_son_los_de_las_fichas() -> None:
    assert registro.disponibles() == [
        "binance",
        "hyperliquid",
        "bybit",
        "okx",
        "kraken",
        "coinbase",
    ]


def test_un_exchange_que_no_existe() -> None:
    with pytest.raises(
        ExchangeError, match=r"No se conoce el exchange 'ftx'. Los que hay: binance"
    ):
        registro.conector_publico("ftx")


def test_una_red_que_no_existe() -> None:
    with pytest.raises(ExchangeError, match="Red desconocida"):
        registro.conector("bybit", "principal")  # type: ignore[arg-type]


def test_sin_activar_no_hay_conector_con_claves() -> None:
    with pytest.raises(ExchangeError, match="Bybit no está activo con dinero real"):
        registro.conector("bybit", "real")
    with pytest.raises(ExchangeError, match="Guarda las claves de la red de pruebas"):
        registro.conector("bybit", "pruebas")
    with pytest.raises(ExchangeError, match="Kraken no tiene red de pruebas"):
        registro.conector("kraken", "pruebas")


def test_activo_en_real_da_el_conector_de_ccxt_con_sus_claves() -> None:
    _activar_kraken_en_real()
    c = registro.conector("kraken", "real")
    assert isinstance(c, ConectorCcxt)
    assert (c.exchange, c.red) == ("kraken", "real")
    assert registro.conector("kraken", "real") is c  # se guarda: no recarga los mercados


def test_el_inyectado_sigue_pasando_por_los_cerrojos() -> None:
    falso = ConectorFalso("kraken", "real")
    with registro.inyectados({"kraken": falso}):
        with pytest.raises(ExchangeError, match="no está activo"):
            registro.conector("kraken", "real")
        _activar_kraken_en_real()
        assert registro.conector("kraken", "real") is falso
        assert registro.conector_publico("kraken") is falso
    assert registro.conector_publico("kraken") is not falso


def test_el_publico_se_construye_sin_red_y_se_guarda() -> None:
    """Construir el objeto de ccxt no habla con nadie (la suite corta la red): solo al pedirle
    algo. Y se guarda uno por exchange."""
    publico = registro.conector_publico("bybit")
    assert isinstance(publico, ConectorCcxt)
    assert publico.red == "real"
    assert registro.conector_publico("bybit") is publico
    with pytest.raises(ExchangeError, match="solo da datos públicos"):
        publico.saldo()


def test_quitar_inyectados_olvida_tambien_los_guardados() -> None:
    publico = registro.conector_publico("bybit")
    registro.quitar_inyectados()
    assert registro.conector_publico("bybit") is not publico


def test_con_claves_es_otro_si_cambian_las_claves() -> None:
    a = registro.con_claves("bybit", "pruebas", CLAVES)
    b = registro.con_claves(
        "bybit", "pruebas", ClavesExchange(valores={"apiKey": "OTRA", "secret": "OTRO"})
    )
    assert a is not b
    assert registro.con_claves("bybit", "pruebas", CLAVES) is a


def test_las_claves_no_salen_en_ningun_repr() -> None:
    c = registro.con_claves("bybit", "pruebas", CLAVES)
    assert "SECRETO-K-1" not in repr(c)
    assert "SECRETO-K-1" not in repr(CLAVES)
    assert BYBIT.id in registro.disponibles()


def test_el_falso_sirve_a_quien_pida_el_conector_publico() -> None:
    falso = ConectorFalso("binance", "real")
    falso.poner_precio("BTC/USDT", Decimal(61000))
    registro.inyectar("binance", falso)
    assert registro.conector_publico("binance").precio("BTC/USDT") == Decimal(61000)

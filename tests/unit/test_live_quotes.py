"""Las cotizaciones en vivo: los parsers puros y el catálogo. Sin red, como toda la suite."""

from __future__ import annotations

import sys
import types
from datetime import UTC, datetime

import pytest

from invest_ll.fetch.catalog import EQUITY_CATALOG
from invest_ll.fetch.live import (
    LiveDataError,
    LiveQuote,
    crypto_tickers,
    quote_from_closes,
    quote_from_ticker,
)

AHORA = datetime(2026, 7, 26, tzinfo=UTC)

MERCADOS: dict[str, dict[str, object]] = {
    "BTC/USDT": {"spot": True, "active": True, "quote": "USDT"},
    "币安人生/USDT": {"spot": True, "active": True, "quote": "USDT"},
    "ETH/BTC": {"spot": True, "active": True, "quote": "BTC"},
    "BTC/USDT:USDT": {"spot": False, "active": True, "quote": "USDT"},
}


class BinanceFalso:
    """Como Binance de verdad: una lista de 500 pares (con símbolos no ASCII) la rechaza."""

    falla_sin_lista = False

    def __init__(self, _config: object) -> None: ...

    def load_markets(self) -> dict[str, dict[str, object]]:
        return MERCADOS

    def fetch_tickers(self, symbols: list[str] | None = None) -> dict[str, dict[str, object]]:
        if symbols is not None or self.falla_sin_lista:
            raise RuntimeError(
                "binance GET https://api.binance.com/api/v3/ticker/24hr?symbols=" + "%22X%22" * 2000
            )
        return {
            "BTC/USDT": {"last": 90000.0, "percentage": 1.0, "quoteVolume": 5e9},
            "币安人生/USDT": {"last": 0.01, "percentage": 3.0, "quoteVolume": 1e6},
            "ETH/BTC": {"last": 0.03, "percentage": 0.0, "quoteVolume": 1.0},
            "BTC/USDT:USDT": {"last": 90010.0, "percentage": 1.0, "quoteVolume": 9e9},
        }


@pytest.fixture
def ccxt_falso(monkeypatch: pytest.MonkeyPatch) -> type[BinanceFalso]:
    modulo = types.ModuleType("ccxt")
    modulo.binance = BinanceFalso  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ccxt", modulo)
    BinanceFalso.falla_sin_lista = False
    return BinanceFalso


class TestCotizacionesDeBinance:
    """Caso real del panel: pedir los 511 pares por nombre hacía que Binance rechazara la
    petición entera, y el error (la URL con los 511 símbolos) salía tal cual en Mercado."""

    def test_pide_todos_y_se_queda_con_los_pares_al_contado_contra_usdt(
        self, ccxt_falso: type[BinanceFalso]
    ) -> None:
        cotizaciones = crypto_tickers()
        assert [q.symbol for q in cotizaciones] == ["BTC/USDT", "币安人生/USDT"]

    def test_un_fallo_se_dice_corto_y_sin_la_url(self, ccxt_falso: type[BinanceFalso]) -> None:
        ccxt_falso.falla_sin_lista = True
        with pytest.raises(LiveDataError) as fallo:
            crypto_tickers()
        texto = str(fallo.value)
        assert len(texto) < 300
        assert "symbols=" not in texto
        assert "binance" in texto


class TestTickerDeCcxt:
    def test_un_ticker_completo_se_convierte(self) -> None:
        q = quote_from_ticker(
            "BTC/USDT",
            {"last": 91234.5, "percentage": -2.1, "quoteVolume": 1_500_000_000.0},
            source="binance",
            fetched_at=AHORA,
        )
        assert q is not None
        assert q.price == 91234.5
        assert q.change_24h_pct == -2.1
        assert q.as_row()["volumen 24h (M)"] == 1500.0

    def test_sin_precio_no_se_inventa_un_cero(self) -> None:
        assert (
            quote_from_ticker("X/USDT", {"last": None}, source="binance", fetched_at=AHORA) is None
        )
        assert quote_from_ticker("X/USDT", {"last": 0}, source="binance", fetched_at=AHORA) is None

    def test_sin_variacion_la_celda_queda_vacia(self) -> None:
        """Un hueco es "no se sabe"; un 0.0 seria "no se movio". No son lo mismo."""
        q = quote_from_ticker("X/USDT", {"last": 5.0}, source="binance", fetched_at=AHORA)
        assert q is not None
        assert q.change_24h_pct is None


class TestCierresDeYfinance:
    def test_dos_cierres_dan_precio_y_variacion(self) -> None:
        q = quote_from_closes(
            "AAPL", [200.0, 210.0], volume=1000.0, source="yfinance", fetched_at=AHORA
        )
        assert q is not None
        assert q.price == 210.0
        assert q.change_24h_pct == 5.0

    def test_un_solo_cierre_da_precio_sin_variacion(self) -> None:
        q = quote_from_closes("AAPL", [200.0], volume=None, source="yfinance", fetched_at=AHORA)
        assert q is not None
        assert q.change_24h_pct is None

    def test_sin_cierres_no_hay_cotizacion(self) -> None:
        assert (
            quote_from_closes("AAPL", [], volume=None, source="yfinance", fetched_at=AHORA) is None
        )

    def test_los_ceros_se_descartan_antes_de_calcular(self) -> None:
        """Un cierre a 0 (fila vacia de yfinance) daria una variacion infinita."""
        q = quote_from_closes(
            "AAPL", [0.0, 200.0, 210.0], volume=None, source="yfinance", fetched_at=AHORA
        )
        assert q is not None
        assert q.change_24h_pct == 5.0


class TestElCatalogo:
    def test_tiene_tamanho_de_verdad(self) -> None:
        """Diez activos "no dan juego": el catalogo existe para que haya donde mirar."""
        assert len(EQUITY_CATALOG) >= 150

    def test_sin_duplicados(self) -> None:
        assert len(EQUITY_CATALOG) == len(set(EQUITY_CATALOG))

    def test_simbolos_normalizados(self) -> None:
        for simbolo in EQUITY_CATALOG:
            assert simbolo == simbolo.strip().upper(), simbolo

    def test_incluye_bolsa_espanhola(self) -> None:
        """El operador es espanhol; su mercado no puede faltar."""
        assert any(s.endswith(".MC") for s in EQUITY_CATALOG)


class TestLaFila:
    def test_as_row_redondea_el_volumen_a_millones(self) -> None:
        q = LiveQuote(
            symbol="AAPL",
            price=210.0,
            change_24h_pct=1.5,
            volume_24h=123_456_789.0,
            source="yfinance",
            fetched_at=AHORA,
        )
        assert q.as_row() == {
            "activo": "AAPL",
            "precio": 210.0,
            "24h %": 1.5,
            "volumen 24h (M)": 123.46,
        }

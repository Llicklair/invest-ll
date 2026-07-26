"""Las cotizaciones en vivo: los parsers puros y el catálogo. Sin red, como toda la suite."""

from __future__ import annotations

from datetime import UTC, datetime

from invest_ll.fetch.catalog import EQUITY_CATALOG
from invest_ll.fetch.live import LiveQuote, quote_from_closes, quote_from_ticker

AHORA = datetime(2026, 7, 26, tzinfo=UTC)


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

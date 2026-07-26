"""Cotizaciones en vivo: una foto del mercado con su hora, pedida cuando se pulsa.

Vive en `fetch/` porque es la capa donde la red está permitida — el motor de backtesting sigue
sin poder tocarla, y estas cotizaciones **no se guardan ni entran en ningún backtest**: son para
mirar. El histórico reproducible sigue viniendo de `invest-ll-fetch`, con su procedencia.

Dos fuentes, las dos gratis y ya integradas en el proyecto:

- **Cripto**: `fetch_tickers()` de ccxt sobre Binance — TODOS los pares spot contra USDT en una
  sola llamada (cientos de activos).
- **Bolsa**: yfinance en lote sobre el catálogo (`catalog.py`), ~170 valores.

"En vivo" aquí significa *al pulsar*: una foto fechada, no un chorro continuo. Es deliberado —
un panel que se refresca solo es una notificación con otro nombre.

Nota sobre tipos: frontera con ccxt/yfinance, que no publican tipado. La comprobación estricta se
relaja SOLO aquí, igual que en `providers/equity.py` — los parsers puros de arriba sí están
tipados y probados.
"""

# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false, reportMissingTypeStubs=false
# pyright: reportAttributeAccessIssue=false, reportIndexIssue=false
# pyright: reportArgumentType=false

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from invest_ll.errors import InvestLLError

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Mapping, Sequence

TIMEOUT_MS = 15_000


class LiveDataError(InvestLLError):
    """No se pudieron traer cotizaciones. La red falla; el resto del panel no."""


@dataclass(frozen=True, slots=True)
class LiveQuote:
    """Una cotización puntual. `float` a propósito: es para mirar, no para contabilizar."""

    symbol: str
    price: float
    change_24h_pct: float | None
    volume_24h: float | None
    source: str
    fetched_at: datetime

    def as_row(self) -> dict[str, object]:
        return {
            "activo": self.symbol,
            "precio": self.price,
            "24h %": self.change_24h_pct,
            "volumen 24h (M)": (
                round(self.volume_24h / 1_000_000, 2) if self.volume_24h is not None else None
            ),
        }


def quote_from_ticker(
    symbol: str, ticker: Mapping[str, object], *, source: str, fetched_at: datetime
) -> LiveQuote | None:
    """Un ticker de ccxt → cotización. Sin precio no hay cotización, no se inventa un 0."""
    ultimo = ticker.get("last")
    if not isinstance(ultimo, int | float) or ultimo <= 0:
        return None
    variacion = ticker.get("percentage")
    volumen = ticker.get("quoteVolume")
    return LiveQuote(
        symbol=symbol,
        price=float(ultimo),
        change_24h_pct=float(variacion) if isinstance(variacion, int | float) else None,
        volume_24h=float(volumen) if isinstance(volumen, int | float) else None,
        source=source,
        fetched_at=fetched_at,
    )


def quote_from_closes(
    symbol: str,
    closes: Sequence[float],
    *,
    volume: float | None,
    source: str,
    fetched_at: datetime,
) -> LiveQuote | None:
    """Cierres recientes → cotización con variación contra el cierre anterior."""
    limpios = [c for c in closes if c and c > 0]
    if not limpios:
        return None
    ultimo = limpios[-1]
    variacion = (ultimo / limpios[-2] - 1) * 100 if len(limpios) >= 2 else None
    return LiveQuote(
        symbol=symbol,
        price=float(ultimo),
        change_24h_pct=round(variacion, 2) if variacion is not None else None,
        volume_24h=float(volume) if volume else None,
        source=source,
        fetched_at=fetched_at,
    )


def crypto_tickers(exchange_id: str = "binance", *, quote: str = "USDT") -> list[LiveQuote]:
    """Todos los pares spot contra `quote` del exchange, en una sola llamada."""
    import ccxt

    ahora = datetime.now(UTC)
    try:
        exchange = getattr(ccxt, exchange_id)({"timeout": TIMEOUT_MS})
        mercados = exchange.load_markets()
        elegibles = {
            simbolo
            for simbolo, mercado in mercados.items()
            if mercado.get("spot")
            and mercado.get("active")
            and mercado.get("quote") == quote
            and ":" not in simbolo
        }
        tickers = exchange.fetch_tickers(list(elegibles))
    except Exception as error:
        raise LiveDataError(f"{exchange_id} no respondio: {error}") from error

    cotizaciones = [
        q
        for simbolo, ticker in tickers.items()
        if (q := quote_from_ticker(simbolo, ticker, source=exchange_id, fetched_at=ahora))
        is not None
    ]
    # Por volumen: lo negociado arriba. Es un orden informativo, no un ranking de "ganadores".
    cotizaciones.sort(key=lambda q: q.volume_24h or 0, reverse=True)
    return cotizaciones


def equity_quotes(tickers: Sequence[str]) -> list[LiveQuote]:
    """Últimos precios del catálogo de bolsa, en lote."""
    import yfinance

    ahora = datetime.now(UTC)
    try:
        datos = yfinance.download(
            list(tickers),
            period="5d",
            interval="1d",
            group_by="ticker",
            progress=False,
            threads=True,
        )
    except Exception as error:
        raise LiveDataError(f"yfinance no respondio: {error}") from error
    if datos is None or datos.empty:
        raise LiveDataError("yfinance devolvio un lote vacio")

    cotizaciones: list[LiveQuote] = []
    for simbolo in tickers:
        try:
            sub = datos[simbolo] if simbolo in datos.columns.get_level_values(0) else None
        except (KeyError, AttributeError):  # pragma: no cover - forma inesperada del lote
            sub = None
        if sub is None:
            continue
        cierres = [float(v) for v in sub["Close"].dropna().tolist()]
        volumenes = sub["Volume"].dropna().tolist()
        cotizacion = quote_from_closes(
            simbolo,
            cierres,
            volume=float(volumenes[-1]) if volumenes else None,
            source="yfinance",
            fetched_at=ahora,
        )
        if cotizacion is not None:
            cotizaciones.append(cotizacion)
    cotizaciones.sort(key=lambda q: q.volume_24h or 0, reverse=True)
    return cotizaciones

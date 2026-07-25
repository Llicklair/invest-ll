"""Proveedor de histórico de cripto sobre `ccxt` (T028).

`ccxt` unifica decenas de exchanges tras la misma llamada y trae control de tasa propio, lo que
resuelve buena parte de FR-014 sin código nuestro. Solo se usan endpoints públicos: no hay
credenciales que proteger, así que el Principio I se cumple por construcción.

Nota sobre tipos: frontera con una librería sin tipado completo. La comprobación estricta se relaja
**solo aquí**, igual que en la capa de datos de la 001.
"""

# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false, reportMissingTypeStubs=false
# pyright: reportAttributeAccessIssue=false, reportUnknownParameterType=false

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from invest_ll.data.bar import Bar, Interval
from invest_ll.fetch.errors import (
    ProviderUnavailableError,
    RateLimitError,
    UnknownSymbolError,
)
from invest_ll.fetch.protocol import ProviderCapabilities

if TYPE_CHECKING:  # pragma: no cover
    pass

# Traducción de nuestros intervalos a los códigos que usa ccxt.
TIMEFRAMES: dict[Interval, str] = {
    Interval.MINUTE_1: "1m",
    Interval.MINUTE_5: "5m",
    Interval.MINUTE_15: "15m",
    Interval.HOUR_1: "1h",
    Interval.HOUR_4: "4h",
    Interval.DAY_1: "1d",
}


class CcxtProvider:
    """Histórico de cripto desde cualquier exchange que soporte `ccxt`."""

    __slots__ = ("_capabilities", "_exchange", "_exchange_id")

    def __init__(self, exchange_id: str = "binance", *, max_bars: int = 1000) -> None:
        import ccxt

        if not hasattr(ccxt, exchange_id):
            raise ValueError(f"ccxt no conoce el exchange {exchange_id!r}")

        # enableRateLimit deja que la propia librería espacie las peticiones. Es preferible a
        # nuestro backoff: conoce los límites concretos de cada exchange.
        self._exchange_id = exchange_id
        self._exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True})
        self._capabilities = ProviderCapabilities(
            name=f"ccxt-{exchange_id}",
            supported_intervals=frozenset(TIMEFRAMES),
            adjusts_prices=True,  # en cripto no hay splits ni dividendos que ajustar
            includes_delisted=False,
            max_bars_per_request=max_bars,
        )

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    def fetch(
        self,
        symbol: str,
        interval: Interval,
        start: datetime,
        end: datetime,
    ) -> Sequence[Bar]:
        """Velas del rango, paginando hasta cubrirlo entero.

        `fetch_ohlcv` devuelve como mucho unos cientos de velas por llamada, así que un año de
        datos horarios necesita varias peticiones encadenadas por marca temporal.
        """
        import ccxt

        timeframe = TIMEFRAMES[interval]
        desde_ms = int(start.timestamp() * 1000)
        hasta_ms = int(end.timestamp() * 1000)
        paso_ms = int(interval.duration.total_seconds() * 1000)

        bars: list[Bar] = []
        cursor = desde_ms

        while cursor < hasta_ms:
            try:
                lote = self._exchange.fetch_ohlcv(
                    symbol, timeframe, since=cursor, limit=self._capabilities.max_bars_per_request
                )
            except ccxt.BadSymbol as error:
                raise UnknownSymbolError(
                    f"{self._exchange_id} no reconoce el activo {symbol!r}"
                ) from error
            except ccxt.RateLimitExceeded as error:
                raise RateLimitError(f"{self._exchange_id}: {error}") from error
            except ccxt.NetworkError as error:
                raise ProviderUnavailableError(f"{self._exchange_id}: {error}") from error

            if not lote:
                break

            for marca, apertura, maximo, minimo, cierre, volumen in lote:
                if marca >= hasta_ms:
                    break
                bars.append(
                    Bar(
                        timestamp=datetime.fromtimestamp(marca / 1000, tz=UTC),
                        open=float(apertura),
                        high=float(maximo),
                        low=float(minimo),
                        close=float(cierre),
                        volume=float(volumen),
                    )
                )

            ultimo = int(lote[-1][0])
            if ultimo < cursor + paso_ms:
                # El exchange no avanza: sin esta salida el bucle sería infinito.
                break
            cursor = ultimo + paso_ms

        return bars

    def __repr__(self) -> str:
        return f"CcxtProvider({self._exchange_id!r})"

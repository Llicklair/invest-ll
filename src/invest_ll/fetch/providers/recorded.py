"""Proveedor de respuestas grabadas (T019).

Existe para que la suite pruebe la lógica de descarga **sin tocar la red** (FR-024). No es un
apaño de test: es la tercera implementación del mismo protocolo, y que exista demuestra que la
abstracción sirve para algo.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING

from invest_ll.data.bar import Bar, Interval
from invest_ll.fetch.errors import RateLimitError, UnknownSymbolError
from invest_ll.fetch.protocol import ProviderCapabilities

if TYPE_CHECKING:  # pragma: no cover
    pass

TODOS_LOS_INTERVALOS = frozenset(Interval)


class RecordedProvider:
    """Devuelve velas prefijadas y cuenta cuántas veces se le ha llamado.

    El contador no es telemetría decorativa: es lo que hace verificable SC-005 —que ampliar un
    rango ya descargado no vuelva a pedir lo que ya se tenía.
    """

    __slots__ = ("_bars", "_capabilities", "_fail_times", "_known", "calls", "requested_ranges")

    def __init__(
        self,
        bars: Sequence[Bar],
        *,
        name: str = "recorded",
        adjusts_prices: bool = True,
        includes_delisted: bool = True,
        supported_intervals: frozenset[Interval] = TODOS_LOS_INTERVALOS,
        max_bars_per_request: int = 1000,
        known_symbols: frozenset[str] | None = None,
        fail_times: int = 0,
    ) -> None:
        self._bars = list(bars)
        self._known = known_symbols
        self._fail_times = fail_times
        self._capabilities = ProviderCapabilities(
            name=name,
            supported_intervals=supported_intervals,
            adjusts_prices=adjusts_prices,
            includes_delisted=includes_delisted,
            max_bars_per_request=max_bars_per_request,
        )
        self.calls: int = 0
        self.requested_ranges: list[tuple[datetime, datetime]] = []

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
        if self._known is not None and symbol not in self._known:
            raise UnknownSymbolError(f"el proveedor no reconoce el activo {symbol!r}")

        self.calls += 1
        self.requested_ranges.append((start, end))

        if self._fail_times > 0:
            self._fail_times -= 1
            raise RateLimitError("límite de peticiones simulado")

        return [bar for bar in self._bars if start <= bar.timestamp < end]

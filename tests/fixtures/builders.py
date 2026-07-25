"""Constructores de series sintéticas para los tests (T019).

Series pequeñas y con resultado predecible: si un test falla, el fallo debe ser del motor, no de
unos datos que nadie entiende.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from invest_ll.data.bar import Bar, Interval
from invest_ll.data.calendars import Continuous24x7, MarketCalendar
from invest_ll.data.series import PriceSeries

ORIGIN = datetime(2026, 1, 1, tzinfo=UTC)


def bar_at(
    ts: datetime,
    close: float,
    *,
    open_: float | None = None,
    high: float | None = None,
    low: float | None = None,
    volume: float = 1000.0,
) -> Bar:
    """Vela coherente construida alrededor de un precio de cierre."""
    o = close if open_ is None else open_
    h = max(o, close) if high is None else high
    lo = min(o, close) if low is None else low
    return Bar(timestamp=ts, open=o, high=h, low=lo, close=close, volume=volume)


def series_from_closes(
    closes: Sequence[float],
    *,
    interval: Interval = Interval.DAY_1,
    calendar: MarketCalendar | None = None,
    symbol: str = "TEST",
    start: datetime = ORIGIN,
) -> PriceSeries:
    """Serie donde cada vela abre y cierra al mismo precio.

    Elimina la ambigüedad intra-vela: cualquier diferencia en el resultado viene del motor.
    """
    step: timedelta = interval.duration
    bars = [bar_at(start + step * i, close) for i, close in enumerate(closes)]
    return PriceSeries(
        symbol=symbol,
        interval=interval,
        calendar=calendar or Continuous24x7(),
        bars=tuple(bars),
    )


def ramp(n: int, *, start: float = 100.0, step: float = 1.0) -> list[float]:
    """Precios que suben en línea recta."""
    return [start + step * i for i in range(n)]


def v_shape(n: int, *, start: float = 100.0, step: float = 1.0) -> list[float]:
    """Precios que bajan y luego suben: fuerza un cruce de medias en ambos sentidos."""
    half = n // 2
    down = [start - step * i for i in range(half)]
    up = [down[-1] + step * (i + 1) for i in range(n - half)]
    return down + up

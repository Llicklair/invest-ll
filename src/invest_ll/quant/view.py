"""What a strategy may see at the close of day `t`: the past, and nothing else.

The guarantee is structural, as in `invest_ll.engine.view`: every accessor slices the arrays at
row `t` inclusive, and there is no accessor that takes an absolute row. A strategy cannot read
tomorrow's open even by mistake. Orders it implies are filled at the next day's open by the engine.
"""

from __future__ import annotations

import warnings

import numpy as np

from invest_ll.quant.panel import FloatArray, Panel
from invest_ll.quant.universe import PointInTimeUniverse

BoolArray = np.ndarray


class MarketView:
    __slots__ = ("_panel", "_t", "_universe")

    def __init__(self, panel: Panel, t: int, universe: PointInTimeUniverse | None = None) -> None:
        if not 0 <= t < len(panel):
            raise IndexError(f"cursor {t} outside the panel (0..{len(panel) - 1})")
        self._panel = panel
        self._t = t
        self._universe = universe

    @property
    def cursor(self) -> int:
        return self._t

    @property
    def symbols(self) -> tuple[str, ...]:
        return self._panel.symbols

    @property
    def n_assets(self) -> int:
        return len(self._panel.symbols)

    @property
    def periods_per_year(self) -> int:
        return self._panel.periods_per_year

    def column(self, symbol: str) -> int:
        return self._panel.column(symbol)

    def members(self) -> BoolArray:
        """Instruments in the universe today; without a universe rule, everything that traded today."""
        if self._universe is not None:
            return self._universe.members(self._t)
        return ~np.isnan(self._panel.close[self._t])

    def last_close(self) -> FloatArray:
        return self._panel.close[self._t].copy()

    def closes(self, lookback: int) -> FloatArray:
        """Closes of the last `lookback + 1` days up to today, oldest first (fewer at the start)."""
        if lookback < 1:
            raise ValueError("lookback must be >= 1")
        lo = max(0, self._t - lookback)
        return self._panel.close[lo : self._t + 1].copy()

    def total_return(self, lookback: int) -> FloatArray:
        """Simple return over the last `lookback` days; NaN where either end is missing."""
        if self._t < lookback:
            return np.full(self.n_assets, np.nan)
        now = self._panel.close[self._t]
        then = self._panel.close[self._t - lookback]
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where((then > 0) & ~np.isnan(now), now / then - 1.0, np.nan)

    def daily_returns(self, lookback: int) -> FloatArray:
        """Daily simple returns of the last `lookback` days, shape (<= lookback, n_assets)."""
        c = self.closes(lookback)
        with np.errstate(divide="ignore", invalid="ignore"):
            return c[1:] / c[:-1] - 1.0

    def volatility(self, lookback: int, min_fraction: float = 0.8) -> FloatArray:
        """Std of daily returns over `lookback` days; NaN with less than `min_fraction` of the data."""
        r = self.daily_returns(lookback)
        enough = np.sum(~np.isnan(r), axis=0) >= max(2, int(min_fraction * lookback))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            sd = np.nanstd(r, axis=0, ddof=1)
        return np.where(enough, sd, np.nan)

    def covariance(self, columns: np.ndarray, lookback: int) -> FloatArray:
        """Covariance of daily returns for the given columns; missing days count as zero return."""
        r = self.daily_returns(lookback)[:, columns]
        r = np.nan_to_num(r, nan=0.0)
        if len(r) < 2:
            return np.zeros((len(columns), len(columns)))
        return np.atleast_2d(np.cov(r, rowvar=False))

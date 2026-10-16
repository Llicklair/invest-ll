"""Strategies as target weights.

A strategy looks at a `MarketView` at the close of a decision day and returns the fraction of the
account it wants in each instrument (non-negative, summing to at most 1; the rest stays in cash).
Returning `None` means "leave the holdings as they are", which is how buy-and-hold is expressed.

The flagship is `MomentumPortfolio`, which applies what can be learned from firms like Quadrature at
a one-person scale:

- **Breadth.** Hold several assets instead of betting everything on one.
- **Robustness over optimisation.** Blend several lookbacks instead of picking the best one, so no
  single parameter carries the result.
- **Risk-based sizing.** Weight by inverse volatility, cap any single position, and scale the whole
  book to a volatility target. Cash is a position.
- **A trend filter per asset.** Only hold what is rising on average across horizons. This is the
  piece of INVEST LL's rotation that survived out-of-sample testing.
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np

from invest_ll.quant.panel import FloatArray
from invest_ll.quant.view import MarketView


@runtime_checkable
class WeightStrategy(Protocol):
    @property
    def name(self) -> str: ...

    def weights(self, view: MarketView) -> FloatArray | None: ...


def _zeros(view: MarketView) -> FloatArray:
    return np.zeros(view.n_assets)


@dataclass(slots=True)
class HoldAsset:
    """Buy one instrument once and keep it."""

    symbol: str
    _done: bool = field(default=False, init=False)

    @property
    def name(self) -> str:
        return f"hold {self.symbol.removesuffix('USDT')}"

    def weights(self, view: MarketView) -> FloatArray | None:
        if self._done:
            return None
        col = view.column(self.symbol)
        if np.isnan(view.last_close()[col]):
            return _zeros(view)
        self._done = True
        w = _zeros(view)
        w[col] = 1.0
        return w


@dataclass(slots=True)
class FixedBasket:
    """Buy a fixed list in equal parts once, then never touch it."""

    symbols: Sequence[str]
    _done: bool = field(default=False, init=False)

    @property
    def name(self) -> str:
        return "hold " + "+".join(s.removesuffix("USDT") for s in self.symbols)

    def weights(self, view: MarketView) -> FloatArray | None:
        if self._done:
            return None
        cols = [view.column(s) for s in self.symbols]
        if np.isnan(view.last_close()[cols]).any():
            return _zeros(view)
        self._done = True
        w = _zeros(view)
        w[cols] = 1.0 / len(cols)
        return w


@dataclass(frozen=True, slots=True)
class EqualWeightUniverse:
    """Everything in the point-in-time universe, equal parts, rebalanced on each decision day.

    This is the honest "market" for a crypto universe: what you get by owning the liquid coins of
    the day without forecasting anything.
    """

    @property
    def name(self) -> str:
        return "equal-weight universe"

    def weights(self, view: MarketView) -> FloatArray | None:
        m = view.members()
        w = _zeros(view)
        if m.any():
            w[m] = 1.0 / m.sum()
        return w


@dataclass(frozen=True, slots=True)
class TrendAsset:
    """One instrument when its `lookback`-day return is positive, cash otherwise."""

    symbol: str
    lookback: int = 30

    @property
    def name(self) -> str:
        return f"{self.symbol.removesuffix('USDT')} trend {self.lookback}d"

    def weights(self, view: MarketView) -> FloatArray | None:
        col = view.column(self.symbol)
        w = _zeros(view)
        r = view.total_return(self.lookback)[col]
        if not np.isnan(r) and r > 0:
            w[col] = 1.0
        return w


@dataclass(frozen=True, slots=True)
class RotationTop1:
    """INVEST LL's current policy, generalised to any universe.

    All capital in the member with the highest `lookback`-day return; cash if that return is below
    `min_return`. With a fixed four-coin universe this reproduces `RelativeMomentum`.
    """

    lookback: int = 30
    min_return: float | None = 0.0

    @property
    def name(self) -> str:
        return f"rotation top-1 {self.lookback}d"

    def weights(self, view: MarketView) -> FloatArray | None:
        w = _zeros(view)
        r = np.where(view.members(), view.total_return(self.lookback), np.nan)
        if np.all(np.isnan(r)):
            return w
        best = int(np.nanargmax(r))
        if self.min_return is not None and r[best] < self.min_return:
            return w
        w[best] = 1.0
        return w


@dataclass(frozen=True, slots=True)
class MomentumPortfolio:
    """Diversified, risk-sized trend portfolio. See the module docstring for the reasoning.

    Score of each member: the average over `lookbacks` of its log return divided by
    (daily volatility x sqrt(lookback)), a t-statistic of the trend. Members whose average log
    return is not positive are dropped (the per-asset trend filter). The best `top_k` by score are
    held, weighted by inverse volatility, each capped at `max_weight`, and the whole book is scaled
    down when its estimated annual volatility exceeds `vol_target`.
    """

    lookbacks: tuple[int, ...] = (14, 30, 60, 90)
    top_k: int = 5
    vol_lookback: int = 60
    max_weight: float = 0.35
    vol_target: float | None = 0.60
    weighting: str = "inverse_vol"  # or "equal"

    def __post_init__(self) -> None:
        if not self.lookbacks or min(self.lookbacks) < 2:
            raise ValueError("lookbacks must be >= 2 days")
        if self.top_k < 1 or not 0 < self.max_weight <= 1:
            raise ValueError("top_k >= 1 and 0 < max_weight <= 1 are required")
        if self.weighting not in {"inverse_vol", "equal"}:
            raise ValueError(f"unknown weighting {self.weighting!r}")

    @property
    def name(self) -> str:
        lb = "/".join(str(x) for x in self.lookbacks)
        vt = f", vol {self.vol_target:.0%}" if self.vol_target else ""
        return f"momentum top-{self.top_k} ({lb}d{vt})"

    def scores(self, view: MarketView) -> tuple[FloatArray, FloatArray]:
        """(score, average log return) per instrument; NaN where not computable."""
        vol = view.volatility(self.vol_lookback)
        zs: list[FloatArray] = []
        logs: list[FloatArray] = []
        for lb in self.lookbacks:
            r = view.total_return(lb)
            with np.errstate(divide="ignore", invalid="ignore"):
                lr = np.log1p(r)
                zs.append(lr / (vol * math.sqrt(lb)))
            logs.append(lr)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            z = np.nanmean(np.vstack(zs), axis=0)
            avg_log = np.nanmean(np.vstack(logs), axis=0)
            available = np.sum(~np.isnan(np.vstack(zs)), axis=0)
        need = max(1, len(self.lookbacks) // 2)
        z = np.where(available >= need, z, np.nan)
        return z, avg_log

    def weights(self, view: MarketView) -> FloatArray | None:
        w = _zeros(view)
        members = view.members()
        z, avg_log = self.scores(view)
        vol = view.volatility(self.vol_lookback)
        ok = (
            members
            & ~np.isnan(z)
            & (np.nan_to_num(avg_log, nan=-1.0) > 0)
            & ~np.isnan(vol)
            & (vol > 0)
        )
        if not ok.any():
            return w
        candidates = np.nonzero(ok)[0]
        order = candidates[np.argsort(-z[candidates], kind="stable")]
        chosen = order[: self.top_k]

        raw = 1.0 / vol[chosen] if self.weighting == "inverse_vol" else np.ones(len(chosen))
        weights = _cap_and_normalise(raw / raw.sum(), self.max_weight)
        # With fewer than 1/max_weight names, the cap leaves part of the book in cash on purpose.

        if self.vol_target is not None:
            cov = view.covariance(chosen, self.vol_lookback)
            est = math.sqrt(max(float(weights @ cov @ weights), 0.0) * view.periods_per_year)
            if est > self.vol_target:
                weights = weights * (self.vol_target / est)

        w[chosen] = weights
        return w


def _cap_and_normalise(weights: FloatArray, cap: float) -> FloatArray:
    """Cap each weight at `cap`, redistributing the excess to uncapped names (sum stays <= 1)."""
    w = weights.astype(np.float64).copy()
    for _ in range(len(w) + 1):
        over = w > cap + 1e-12
        if not over.any():
            break
        excess = float(np.sum(w[over] - cap))
        w[over] = cap
        free = ~over & (w < cap - 1e-12)
        if not free.any() or excess <= 0:
            break
        w[free] += excess * w[free] / w[free].sum()
    return np.minimum(w, cap)

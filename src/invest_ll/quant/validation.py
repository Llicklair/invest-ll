"""Is the result skill or luck? Three tests that a single backtest cannot answer.

1. **Walk-forward selection.** Each year, pick the configuration that did best in all the years
   before it, and record how that pick does in the year it was not chosen on. Stitched together,
   these years are what a person following the procedure would have lived through. It is the honest
   version of "I tested 40 settings and this one works".
2. **Probability of backtest overfitting (PBO)**, by combinatorially symmetric cross-validation
   (Bailey, Borwein, López de Prado and Zhu, 2014). Split time into S blocks; for every way of
   choosing half of them as "in sample", find the best configuration there and see where it ranks
   in the other half. PBO is the share of splits where the in-sample winner falls below the median
   out of sample. Around 0.5 means picking the best configuration is no better than picking at
   random.
3. **Block bootstrap** confidence intervals for CAGR and Sharpe: resample blocks of days to see how
   much the headline numbers move with a slightly different history.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations

import numpy as np

from invest_ll.quant.metrics import per_period_sharpe
from invest_ll.quant.panel import FloatArray


@dataclass(frozen=True, slots=True)
class WalkForwardStep:
    year: int
    chosen: str
    train_sharpe: float
    test_return: float


@dataclass(frozen=True, slots=True)
class WalkForward:
    steps: tuple[WalkForwardStep, ...]
    returns: FloatArray  # stitched out-of-sample daily returns
    days: np.ndarray

    @property
    def distinct_choices(self) -> int:
        return len({s.chosen for s in self.steps})


def walk_forward(
    names: Sequence[str],
    returns: FloatArray,
    years: np.ndarray,
    *,
    min_train_years: int = 2,
    days: np.ndarray | None = None,
) -> WalkForward:
    """Annual walk-forward over a (T, N) matrix of daily returns of N configurations.

    `years[i]` is the calendar year of row i. For each year Y with at least `min_train_years` of
    history before it, the configuration with the best Sharpe on rows before Y is applied to Y.
    Switching configuration at a year boundary is assumed free; with yearly switches this is small.
    """
    if returns.shape != (len(years), len(names)):
        raise ValueError("returns must be (len(years), len(names))")
    uniq = sorted({int(y) for y in years})
    steps: list[WalkForwardStep] = []
    stitched: list[FloatArray] = []
    stitched_days: list[np.ndarray] = []
    for year in uniq[min_train_years:]:
        train = years < year
        test = years == year
        if train.sum() < 60 or test.sum() == 0:
            continue
        scores = np.array([per_period_sharpe(returns[train, j]) for j in range(len(names))])
        best = int(np.argmax(scores))
        r: FloatArray = np.asarray(returns[test, best], dtype=np.float64)
        steps.append(
            WalkForwardStep(
                year=year,
                chosen=names[best],
                train_sharpe=float(scores[best]),
                test_return=float(np.prod(1.0 + r)) - 1.0,
            )
        )
        stitched.append(r)
        if days is not None:
            stitched_days.append(days[test])
    out = np.concatenate(stitched) if stitched else np.array([])
    out_days = np.concatenate(stitched_days) if stitched_days else np.array([], dtype=np.int64)
    return WalkForward(steps=tuple(steps), returns=out, days=out_days)


@dataclass(frozen=True, slots=True)
class PBO:
    probability: float
    splits: int
    median_logit: float
    oos_loss_rate: float  # share of splits where the IS winner lost money out of sample


def probability_of_overfitting(returns: FloatArray, blocks: int = 16) -> PBO:
    """CSCV estimate of PBO for a (T, N) matrix of per-period returns of N configurations."""
    t_count, n = returns.shape
    if n < 2:
        raise ValueError("PBO needs at least two configurations")
    if blocks % 2 or blocks < 4:
        raise ValueError("blocks must be an even number >= 4")
    size = t_count // blocks
    parts = [returns[i * size : (i + 1) * size] for i in range(blocks)]
    logits: list[float] = []
    losses = 0
    for chosen in combinations(range(blocks), blocks // 2):
        rest = [i for i in range(blocks) if i not in chosen]
        ins = np.vstack([parts[i] for i in chosen])
        oos = np.vstack([parts[i] for i in rest])
        is_sr = _sharpes(ins)
        oos_sr = _sharpes(oos)
        best = int(np.argmax(is_sr))
        # Relative rank of the IS winner among all configurations out of sample, in (0, 1).
        ref = float(oos_sr[best])
        below = int(np.count_nonzero(oos_sr < ref))
        ties = int(np.count_nonzero(oos_sr == ref)) - 1
        rank = (below + 0.5 * ties + 1) / (n + 1)
        logits.append(math.log(rank / (1 - rank)))
        if float(np.sum(oos[:, best])) < 0:
            losses += 1
    arr = np.array(logits)
    return PBO(
        probability=float(np.mean(arr <= 0)),
        splits=len(logits),
        median_logit=float(np.median(arr)),
        oos_loss_rate=losses / len(logits),
    )


def _sharpes(block: FloatArray) -> FloatArray:
    sd = block.std(axis=0, ddof=1)
    mean = block.mean(axis=0)
    return np.where(sd > 0, mean / np.where(sd > 0, sd, 1.0), 0.0)


@dataclass(frozen=True, slots=True)
class Interval:
    low: float
    median: float
    high: float


def bootstrap(
    returns: FloatArray,
    periods_per_year: int,
    *,
    block: int = 20,
    samples: int = 2000,
    seed: int = 7,
) -> tuple[Interval, Interval]:
    """90% intervals for (CAGR, Sharpe) by stationary block bootstrap. Deterministic by seed."""
    rng = np.random.default_rng(seed)
    n = len(returns)
    if n < block * 2:
        nan = Interval(float("nan"), float("nan"), float("nan"))
        return nan, nan
    cagrs = np.empty(samples)
    sharpes = np.empty(samples)
    years = n / periods_per_year
    for k in range(samples):
        idx = np.empty(n, dtype=np.int64)
        pos = 0
        while pos < n:
            start = int(rng.integers(0, n))
            length = int(rng.geometric(1 / block))
            take = min(length, n - pos)
            idx[pos : pos + take] = (start + np.arange(take)) % n
            pos += take
        sample = returns[idx]
        growth = float(np.prod(1 + sample))
        cagrs[k] = growth ** (1 / years) - 1 if growth > 0 else -1.0
        sd = float(sample.std(ddof=1))
        sharpes[k] = float(sample.mean()) / sd * math.sqrt(periods_per_year) if sd > 0 else 0.0

    def interval(x: FloatArray) -> Interval:
        lo, med, hi = np.percentile(x, [5, 50, 95])
        return Interval(float(lo), float(med), float(hi))

    return interval(cagrs), interval(sharpes)

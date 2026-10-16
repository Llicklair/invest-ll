"""The crypto study: one pre-registered strategy, honest benchmarks, and the luck tests.

**Pre-registration.** `FLAGSHIP` below was fixed before running anything on the full universe, with
textbook values rather than tuned ones (a blend of 2-week to 3-month trends, five names, inverse
volatility, a 35% cap and a 60% volatility target). The grid around it exists to measure how fragile
it is, not to pick a better one. Picking the best cell of the grid afterwards would be exactly the
mistake the deflated Sharpe ratio and PBO are here to price.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from itertools import product

import numpy as np

from invest_ll.quant.engine import BINANCE_SPOT, Costs, RunConfig, RunResult, run
from invest_ll.quant.metrics import Summary, deflated_sharpe, per_period_sharpe, summarise
from invest_ll.quant.panel import FloatArray, Panel
from invest_ll.quant.strategies import (
    EqualWeightUniverse,
    HoldAsset,
    MomentumPortfolio,
    RotationTop1,
    TrendAsset,
    WeightStrategy,
)
from invest_ll.quant.universe import PointInTimeUniverse, UniverseRule
from invest_ll.quant.validation import (
    PBO,
    Interval,
    WalkForward,
    bootstrap,
    probability_of_overfitting,
    walk_forward,
)

FLAGSHIP = MomentumPortfolio(
    lookbacks=(14, 30, 60, 90), top_k=5, vol_lookback=60, max_weight=0.35, vol_target=0.60
)
FLAGSHIP_UNIVERSE = UniverseRule(top_n=20, window=30, min_history=60, min_quote_volume=1_000_000)
FLAG_KEY = "Momentum portfolio (pre-registered)"
REBALANCE_EVERY = 7
TRANCHES = 7
CAPITAL = 10_000.0


@dataclass(frozen=True, slots=True)
class GridPoint:
    label: str
    strategy: MomentumPortfolio
    universe: UniverseRule


def default_grid() -> list[GridPoint]:
    """81 neighbours of the flagship: lookback sets x names held x volatility target x universe size."""
    points: list[GridPoint] = []
    lookback_sets = {"30d": (30,), "14-90d": (14, 30, 60, 90), "60-120d": (60, 120)}
    for (lb_name, lbs), k, vt, n in product(
        lookback_sets.items(), (3, 5, 8), (None, 0.4, 0.6), (10, 20, 40)
    ):
        strategy = MomentumPortfolio(
            lookbacks=lbs, top_k=k, vol_lookback=60, max_weight=0.35, vol_target=vt
        )
        rule = UniverseRule(top_n=n, window=30, min_history=60, min_quote_volume=1_000_000)
        vt_name = f"vol {vt:.0%}" if vt else "no vol target"
        points.append(GridPoint(f"{lb_name}, top {k}, {vt_name}, universe {n}", strategy, rule))
    return points


@dataclass(slots=True)
class StudyResult:
    start: str
    end: str
    runs: dict[str, RunResult] = field(default_factory=lambda: dict[str, RunResult]())
    summaries: dict[str, Summary] = field(default_factory=lambda: dict[str, Summary]())
    grid_labels: list[str] = field(default_factory=lambda: list[str]())
    grid_summaries: list[Summary] = field(default_factory=lambda: list[Summary]())
    walk: WalkForward | None = None
    pbo: PBO | None = None
    deflated: float = float("nan")
    flagship_cagr: Interval | None = None
    flagship_sharpe: Interval | None = None
    weekday_spread: list[float] = field(default_factory=lambda: list[float]())
    capacity: dict[str, Summary] = field(default_factory=lambda: dict[str, Summary]())
    holdout: dict[str, Summary] = field(default_factory=lambda: dict[str, Summary]())
    universe_samples: dict[str, list[str]] = field(default_factory=lambda: dict[str, list[str]]())


def _year(day: int) -> int:
    return datetime.fromtimestamp(day * 86_400, UTC).year


def run_study(
    panel: Panel,
    *,
    start: date = date(2018, 1, 1),
    holdout_start: date = date(2025, 1, 1),
    costs: Costs = BINANCE_SPOT,
    grid: list[GridPoint] | None = None,
    progress: Callable[[str], None] | None = None,
) -> StudyResult:
    def say(message: str) -> None:
        if progress is not None:
            progress(message)

    first = panel.index_of(start)
    p = panel.slice_rows(max(0, first - 200), len(panel))  # 200 days of warm-up for lookbacks
    s0 = p.index_of(start)
    cfg = RunConfig(
        initial_capital=CAPITAL, rebalance_every=REBALANCE_EVERY, tranches=TRANCHES, start=s0
    )
    universes: dict[UniverseRule, PointInTimeUniverse] = {}

    def universe(rule: UniverseRule) -> PointInTimeUniverse:
        if rule not in universes:
            universes[rule] = PointInTimeUniverse(p, rule)
        return universes[rule]

    out = StudyResult(start=p.date_at(s0).isoformat(), end=p.date_at(len(p) - 1).isoformat())

    def go(
        key: str,
        strategy: WeightStrategy | list[WeightStrategy],
        config: RunConfig,
        rule: UniverseRule | None,
    ) -> RunResult:
        say(f"running {key}")
        result = run(p, strategy, costs, config, universe(rule) if rule else None, name=key)
        out.runs[key] = result
        return result

    single = RunConfig(initial_capital=CAPITAL, rebalance_every=REBALANCE_EVERY, start=s0)
    btc = go("Hold BTC", HoldAsset("BTCUSDT"), single, None)
    go(
        "Hold the top 20 (equal weight, monthly)",
        EqualWeightUniverse(),
        RunConfig(initial_capital=CAPITAL, rebalance_every=30, start=s0),
        FLAGSHIP_UNIVERSE,
    )
    go("BTC 30-day trend (weekly)", TrendAsset("BTCUSDT", 30), cfg, None)
    go(
        "INVEST LL policy on the top 20 (top-1, 30d, weekly)",
        RotationTop1(30, 0.0),
        cfg,
        FLAGSHIP_UNIVERSE,
    )
    flagship = go(FLAG_KEY, FLAGSHIP, cfg, FLAGSHIP_UNIVERSE)
    taxed_cfg = RunConfig(
        initial_capital=CAPITAL,
        rebalance_every=REBALANCE_EVERY,
        tranches=TRANCHES,
        start=s0,
        pay_tax=True,
    )
    go("Momentum portfolio, Spanish tax paid yearly", FLAGSHIP, taxed_cfg, FLAGSHIP_UNIVERSE)

    for key, result in out.runs.items():
        out.summaries[key] = summarise(result, btc)

    # Timing luck without tranches.
    say("weekday spread")
    for phase in range(REBALANCE_EVERY):
        r = run(
            p,
            FLAGSHIP,
            costs,
            RunConfig(initial_capital=CAPITAL, rebalance_every=REBALANCE_EVERY, start=s0 + phase),
            universe(FLAGSHIP_UNIVERSE),
        )
        out.weekday_spread.append(float(r.equity[-1] / r.equity[s0] * CAPITAL))

    # Capacity: the same strategy with a bigger account pays more market impact.
    for capital in (10_000.0, 1_000_000.0, 10_000_000.0):
        say(f"capacity {capital:,.0f}")
        r = run(
            p,
            FLAGSHIP,
            costs,
            RunConfig(
                initial_capital=capital,
                rebalance_every=REBALANCE_EVERY,
                tranches=TRANCHES,
                start=s0,
            ),
            universe(FLAGSHIP_UNIVERSE),
        )
        out.capacity[f"{capital:,.0f}"] = summarise(r, btc)

    # Grid, walk-forward, PBO, deflated Sharpe.
    points = grid if grid is not None else default_grid()
    columns: list[FloatArray] = []
    for i, gp in enumerate(points, start=1):
        say(f"grid {i}/{len(points)}: {gp.label}")
        r = run(p, gp.strategy, costs, cfg, universe(gp.universe), name=gp.label)
        out.grid_labels.append(gp.label)
        out.grid_summaries.append(summarise(r, btc))
        columns.append(r.returns)
    if len(columns) >= 2:
        matrix = np.column_stack(columns)
        years = np.array([_year(int(d)) for d in p.days[s0 + 1 :]])
        out.walk = walk_forward(out.grid_labels, matrix, years, days=p.days[s0 + 1 :])
        say("PBO")
        out.pbo = probability_of_overfitting(matrix, blocks=16)
        trials = np.array([per_period_sharpe(matrix[:, j]) for j in range(matrix.shape[1])])
        out.deflated = deflated_sharpe(flagship.returns, trials)

    out.flagship_cagr, out.flagship_sharpe = bootstrap(flagship.returns, p.periods_per_year)

    # The project's reserved stretch, measured on its own.
    h0 = p.index_of(holdout_start)
    for key in (
        "Hold BTC",
        "Hold the top 20 (equal weight, monthly)",
        "INVEST LL policy on the top 20 (top-1, 30d, weekly)",
        "Momentum portfolio (pre-registered)",
    ):
        r = out.runs[key]
        out.holdout[key] = summarise(_rebase(r, h0), _rebase(btc, h0))

    for when in (
        "2018-01-01",
        "2021-01-01",
        "2022-06-01",
        "2024-01-01",
        p.date_at(len(p) - 1).isoformat(),
    ):
        t = min(p.index_of(date.fromisoformat(when)), len(p) - 1)
        m = universe(FLAGSHIP_UNIVERSE).members(t)
        out.universe_samples[p.date_at(t).isoformat()] = [
            p.symbols[j].removesuffix("USDT") for j in np.nonzero(m)[0]
        ]
    return out


def _rebase(result: RunResult, start: int) -> RunResult:
    """The same run, measured from row `start` (equity curve unchanged, metrics start there)."""
    return RunResult(
        name=result.name,
        days=result.days,
        equity=result.equity,
        weights=result.weights,
        turnover=result.turnover,
        costs=result.costs,
        taxes=result.taxes,
        trades=result.trades,
        symbols=result.symbols,
        periods_per_year=result.periods_per_year,
        final_after_liquidation_tax=result.final_after_liquidation_tax,
        start=start,
        notes=result.notes,
    )

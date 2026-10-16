"""The equity study: does risk-based allocation beat buying and holding, risk for risk?

INVEST LL concluded "do not trade equities" because seven strategies on eight ETFs ended with less
money than buy-and-hold. That compares end values only. A fund would compare return per unit of
risk, because risk can be added or removed afterwards with the cash share: a strategy with half the
return and a third of the drawdown can be the better one.

**Pre-registration**, fixed before running: eight asset-class ETFs, monthly decisions in three
staggered tranches, 0.1% commission and 0.05% slippage, cash parked in short Treasuries (SHY). Three
references (SPY, 60/40, equal weight) and three candidates (risk parity, risk parity with a trend
filter, and the crypto momentum portfolio adapted to monthly horizons and a 12% volatility target).
US-listed ETFs stand in for the UCITS equivalents a Spanish investor would buy.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from invest_ll.quant.engine import Costs, RunConfig, RunResult, run
from invest_ll.quant.metrics import Summary, deflated_sharpe, per_period_sharpe, summarise
from invest_ll.quant.panel import Panel
from invest_ll.quant.strategies import (
    CashSleeve,
    ConstantMix,
    HoldAsset,
    MomentumPortfolio,
    RiskParity,
    WeightStrategy,
)
from invest_ll.quant.validation import Interval, bootstrap

ASSETS = ("SPY", "EFA", "EEM", "IEF", "TLT", "GLD", "DBC", "VNQ")
CASH = "SHY"
MONTH = 21
TRANCHES = 3
ETF_COSTS = Costs(commission=0.001, slippage=0.0005, impact=0.0, min_trade=10.0)
CAPITAL = 10_000.0
TREND = (21, 63, 126, 252)


def strategies() -> dict[str, tuple[WeightStrategy, bool]]:
    """Name -> (strategy, is_candidate). References are not counted as trials."""
    return {
        "Hold SPY": (HoldAsset("SPY"), False),
        "60/40 SPY/IEF (monthly)": (ConstantMix((("SPY", 0.6), ("IEF", 0.4)), "60/40"), False),
        "Equal weight, 8 ETFs (monthly)": (
            ConstantMix(tuple((s, 1 / len(ASSETS)) for s in ASSETS), "equal weight"),
            False,
        ),
        "Risk parity": (RiskParity(ASSETS, vol_lookback=63), True),
        "Risk parity + trend filter": (
            CashSleeve(RiskParity(ASSETS, vol_lookback=63, trend_lookbacks=TREND), CASH),
            True,
        ),
        "Momentum top 4, vol 12%": (
            CashSleeve(
                MomentumPortfolio(
                    lookbacks=TREND, top_k=4, vol_lookback=63, max_weight=0.35, vol_target=0.12
                ),
                CASH,
            ),
            True,
        ),
    }


@dataclass(slots=True)
class EtfStudy:
    start: str
    end: str
    runs: dict[str, RunResult] = field(default_factory=lambda: dict[str, RunResult]())
    summaries: dict[str, Summary] = field(default_factory=lambda: dict[str, Summary]())
    holdout: dict[str, Summary] = field(default_factory=lambda: dict[str, Summary]())
    deflated: dict[str, float] = field(default_factory=lambda: dict[str, float]())
    sharpe_interval: dict[str, Interval] = field(default_factory=lambda: dict[str, Interval]())


def run_etf_study(
    panel: Panel,
    *,
    start: date = date(2008, 1, 1),
    holdout_start: date = date(2025, 1, 1),
    progress: Callable[[str], None] | None = None,
) -> EtfStudy:
    s0 = panel.index_of(start)
    out = EtfStudy(
        start=panel.date_at(s0).isoformat(), end=panel.date_at(len(panel) - 1).isoformat()
    )
    spy: RunResult | None = None
    candidates: list[str] = []
    for key, (strategy, is_candidate) in strategies().items():
        if progress is not None:
            progress(f"running {key}")
        hold = isinstance(strategy, HoldAsset)
        config = RunConfig(
            initial_capital=CAPITAL,
            rebalance_every=MONTH,
            tranches=1 if hold else TRANCHES,
            start=s0,
        )
        result = run(panel, strategy, ETF_COSTS, config, None, name=key)
        out.runs[key] = result
        if key == "Hold SPY":
            spy = result
        if is_candidate:
            candidates.append(key)
    for key, result in out.runs.items():
        out.summaries[key] = summarise(result, spy)
        out.sharpe_interval[key] = bootstrap(result.returns, panel.periods_per_year)[1]
    trials = np.array([per_period_sharpe(out.runs[k].returns) for k in candidates])
    for key in candidates:
        out.deflated[key] = deflated_sharpe(out.runs[key].returns, trials)
    h0 = panel.index_of(holdout_start)
    for key, result in out.runs.items():
        out.holdout[key] = summarise(_from(result, h0), None if spy is None else _from(spy, h0))
    return out


def _from(result: RunResult, start: int) -> RunResult:
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


def load_etf_panel(path: str) -> Panel:
    """Panel of exchange sessions from the parquet written by the ETF download."""
    import pandas as pd

    from invest_ll.quant.panel import from_long

    frame = pd.read_parquet(path)  # pyright: ignore[reportUnknownMemberType]
    return from_long(frame, periods_per_year=252, contiguous_days=False, max_gap=10)

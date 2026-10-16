"""Risk-adjusted metrics, and the statistics that say whether a Sharpe ratio means anything.

INVEST LL's reports compare end values and drawdowns in currency. On a compounding curve that hides
the risk taken: "-1.8 million" says nothing without the peak it fell from. Everything here is in
percentages and per-year terms so different strategies, periods and capitals compare directly.

The probabilistic and deflated Sharpe ratios follow Bailey and López de Prado ("The Sharpe Ratio
Efficient Frontier", 2012; "The Deflated Sharpe Ratio", 2014). The deflated version answers the
question this project keeps asking in prose: after trying N configurations, how likely is it that
the best one has a real edge?
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from statistics import NormalDist

import numpy as np

from invest_ll.quant.engine import RunResult
from invest_ll.quant.panel import FloatArray

EULER_GAMMA = 0.5772156649015329
_N = NormalDist()


@dataclass(frozen=True, slots=True)
class Summary:
    name: str
    start: str
    end: str
    years: float
    final_value: float
    final_after_tax: float
    cagr: float
    volatility: float
    sharpe: float
    sortino: float
    max_drawdown: float
    calmar: float
    longest_drawdown_days: int
    time_under_water: float
    exposure: float
    turnover_per_year: float
    cost_drag: float
    tax_paid: float
    trades: int
    beta: float | None
    correlation: float | None
    best_month: float
    worst_month: float
    positive_months: float
    psr: float

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def drawdown(equity: FloatArray) -> FloatArray:
    """Fractional drawdown from the running peak (0 at a new high, negative below it)."""
    peak = np.maximum.accumulate(equity)
    return equity / peak - 1.0


def longest_drawdown(equity: FloatArray) -> int:
    """Longest run of periods spent below a previous peak."""
    under = drawdown(equity) < -1e-12
    best = run = 0
    for flag in under:
        run = run + 1 if flag else 0
        best = max(best, run)
    return best


def sharpe(returns: FloatArray, periods_per_year: int) -> float:
    sd = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0
    return float(np.mean(returns)) / sd * math.sqrt(periods_per_year) if sd > 0 else 0.0


def sortino(returns: FloatArray, periods_per_year: int) -> float:
    downside = np.minimum(returns, 0.0)
    dd = math.sqrt(float(np.mean(downside**2))) if len(returns) else 0.0
    return float(np.mean(returns)) / dd * math.sqrt(periods_per_year) if dd > 0 else 0.0


def probabilistic_sharpe(returns: FloatArray, benchmark_sr: float = 0.0) -> float:
    """P(true per-period Sharpe > benchmark_sr) given the sample's length, skew and kurtosis."""
    n = len(returns)
    if n < 3:
        return float("nan")
    sd = float(np.std(returns, ddof=1))
    if sd == 0:
        return float("nan")
    sr = float(np.mean(returns)) / sd
    z = (returns - returns.mean()) / sd
    skew = float(np.mean(z**3))
    kurt = float(np.mean(z**4))
    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr**2
    if denom <= 0:
        return float("nan")
    return _N.cdf((sr - benchmark_sr) * math.sqrt(n - 1) / math.sqrt(denom))


def expected_max_sharpe(trial_sharpes: FloatArray) -> float:
    """Expected maximum per-period Sharpe among N skill-less trials with the observed dispersion."""
    n = len(trial_sharpes)
    if n < 2:
        return 0.0
    sd = float(np.std(trial_sharpes, ddof=1))
    return sd * (
        (1 - EULER_GAMMA) * _N.inv_cdf(1 - 1.0 / n)
        + EULER_GAMMA * _N.inv_cdf(1 - 1.0 / (n * math.e))
    )


def deflated_sharpe(returns: FloatArray, trial_sharpes: FloatArray) -> float:
    """Probability that the chosen strategy's Sharpe beats the best of N skill-less trials.

    `trial_sharpes` are the per-period (not annualised) Sharpe ratios of every configuration tried,
    the chosen one included. A value below 0.95 means the result is compatible with luck.
    """
    return probabilistic_sharpe(returns, expected_max_sharpe(trial_sharpes))


def per_period_sharpe(returns: FloatArray) -> float:
    sd = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0
    return float(np.mean(returns)) / sd if sd > 0 else 0.0


def monthly_returns(days: np.ndarray, equity: FloatArray) -> dict[tuple[int, int], float]:
    """Return per calendar month, from month-end to month-end values."""
    import datetime as dt

    out: dict[tuple[int, int], float] = {}
    prev_val: float | None = None
    prev_key: tuple[int, int] | None = None
    last_val = float(equity[0])
    for d, v in zip(days, equity, strict=True):
        date = dt.datetime.fromtimestamp(int(d) * 86_400, dt.UTC).date()
        key = (date.year, date.month)
        if prev_key is not None and key != prev_key:
            base = prev_val if prev_val is not None else last_val
            out[prev_key] = last_val / base - 1.0 if base > 0 else 0.0
            prev_val = last_val
        elif prev_key is None:
            prev_val = float(v)
        prev_key = key
        last_val = float(v)
    if prev_key is not None and prev_val is not None:
        out[prev_key] = last_val / prev_val - 1.0 if prev_val > 0 else 0.0
    return out


def summarise(result: RunResult, benchmark: RunResult | None = None) -> Summary:
    """All headline numbers for one run, measured from its first active day."""
    import datetime as dt

    s = result.start
    eq = result.equity[s:]
    rets = result.returns
    ppy = result.periods_per_year
    years = max((len(eq) - 1) / ppy, 1e-9)
    final = float(eq[-1])
    initial = float(eq[0])
    cagr = (final / initial) ** (1 / years) - 1 if initial > 0 and final > 0 else -1.0
    vol = float(np.std(rets, ddof=1)) * math.sqrt(ppy) if len(rets) > 1 else 0.0
    dd = drawdown(eq)
    max_dd = float(dd.min()) if len(dd) else 0.0
    months = list(monthly_returns(result.days[s:], eq).values())

    beta = corr = None
    if benchmark is not None:
        b = benchmark.equity[s:]
        brets = b[1:] / b[:-1] - 1.0
        if len(brets) == len(rets) and np.std(brets) > 0 and np.std(rets) > 0:
            cov = np.cov(rets, brets)
            beta = float(cov[0, 1] / cov[1, 1])
            corr = float(np.corrcoef(rets, brets)[0, 1])

    avg_equity = float(np.mean(eq)) if len(eq) else 1.0

    def day(i: int) -> str:
        return dt.datetime.fromtimestamp(int(result.days[i]) * 86_400, dt.UTC).date().isoformat()

    return Summary(
        name=result.name,
        start=day(s),
        end=day(len(result.days) - 1),
        years=years,
        final_value=final,
        final_after_tax=result.final_after_liquidation_tax,
        cagr=cagr,
        volatility=vol,
        sharpe=sharpe(rets, ppy),
        sortino=sortino(rets, ppy),
        max_drawdown=max_dd,
        calmar=cagr / abs(max_dd) if max_dd < 0 else 0.0,
        longest_drawdown_days=longest_drawdown(eq),
        time_under_water=float(np.mean(dd < -1e-12)) if len(dd) else 0.0,
        exposure=float(np.mean(result.exposure)) if len(eq) else 0.0,
        turnover_per_year=float(np.sum(result.turnover[s:])) / years,
        cost_drag=float(np.sum(result.costs[s:])) / avg_equity / years,
        tax_paid=float(np.sum(result.taxes[s:])),
        trades=result.trades,
        beta=beta,
        correlation=corr,
        best_month=max(months) if months else 0.0,
        worst_month=min(months) if months else 0.0,
        positive_months=float(np.mean([m > 0 for m in months])) if months else 0.0,
        psr=probabilistic_sharpe(rets),
    )

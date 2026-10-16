"""The equity study runs end to end on synthetic sessions."""

from __future__ import annotations

from datetime import date

import numpy as np

from invest_ll.quant.etf_study import ASSETS, CASH, run_etf_study
from invest_ll.quant.panel import Panel

from .builders import DAY0


def test_runs_every_strategy_and_counts_only_candidates_as_trials() -> None:
    rng = np.random.default_rng(5)
    symbols = (*ASSETS, CASH)
    n_days = 900
    closes = 100 * np.cumprod(1 + rng.normal(0.0003, 0.01, size=(n_days, len(symbols))), axis=0)
    panel = Panel(
        days=np.arange(DAY0, DAY0 + n_days, dtype=np.int64),
        symbols=symbols,
        open=closes,
        high=closes,
        low=closes,
        close=closes,
        quote_volume=np.full(closes.shape, 1e9),
        periods_per_year=252,
    )
    study = run_etf_study(panel, start=date(2024, 12, 1), holdout_start=date(2025, 6, 1))
    assert set(study.summaries) >= {"Hold SPY", "60/40 SPY/IEF (monthly)", "Risk parity"}
    assert set(study.deflated) == {
        "Risk parity",
        "Risk parity + trend filter",
        "Momentum top 4, vol 12%",
    }
    for summary in study.summaries.values():
        assert summary.final_value > 0

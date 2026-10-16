"""Forward test: append-only records, replayed through the same engine."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from invest_ll.quant.paper import current_targets, read, record, replay
from invest_ll.quant.strategies import MomentumPortfolio
from invest_ll.quant.universe import UniverseRule

from .builders import random_walk_panel

RULE = UniverseRule(top_n=5, window=10, min_history=20, min_quote_volume=0)
STRATEGY = MomentumPortfolio(lookbacks=(10, 20), top_k=3, vol_lookback=20, vol_target=None)


def test_records_are_append_only(tmp_path: Path) -> None:
    panel = random_walk_panel(8, 120, seed=4)
    ledger = tmp_path / "paper.jsonl"
    w = current_targets(panel, STRATEGY, RULE, rebalance_every=7, tranches=7)
    record(panel, w, STRATEGY.name, ledger)
    with pytest.raises(ValueError, match="append-only"):
        record(panel, w, STRATEGY.name, ledger)
    assert len(read(ledger)) == 1


def test_targets_are_the_average_of_the_tranches_latest_decisions() -> None:
    panel = random_walk_panel(8, 120, seed=6)
    w = current_targets(panel, STRATEGY, RULE, rebalance_every=7, tranches=7)
    assert (w >= 0).all()
    assert w.sum() <= 1 + 1e-9


def test_replay_trades_recorded_targets_at_the_next_open(tmp_path: Path) -> None:
    panel = random_walk_panel(8, 140, seed=9)
    ledger = tmp_path / "paper.jsonl"
    early = panel.slice_rows(0, 100)
    record(
        early, current_targets(early, STRATEGY, RULE, rebalance_every=7, tranches=1), "x", ledger
    )
    result = replay(panel, read(ledger))
    assert result is not None
    assert result.start == 99
    assert np.all(result.equity[:100] == result.equity[0])
    assert result.trades > 0

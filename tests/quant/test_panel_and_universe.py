"""Reference data: reused tickers are split, and the universe only uses the past."""

from __future__ import annotations

import numpy as np
import pandas as pd

from invest_ll.quant.panel import from_long, split_segments
from invest_ll.quant.universe import PointInTimeUniverse, UniverseRule, exclusion_reason

from .builders import DAY0, random_walk_panel


def test_a_long_gap_splits_a_reused_ticker_into_two_instruments() -> None:
    """LUNAUSDT: the original coin until its collapse, a different coin after the gap."""
    old = [(DAY0 + i, 80.0 - i) for i in range(10)]
    new = [(DAY0 + 30 + i, 8.0 + i) for i in range(5)]
    rows = pd.DataFrame(
        [
            {
                "symbol": "LUNAUSDT",
                "day": d,
                "open": p,
                "high": p,
                "low": p,
                "close": p,
                "quote_volume": 1e6,
            }
            for d, p in [*old, *new]
        ]
    )
    panel = from_long(rows)

    assert panel.symbols == ("LUNAUSDT", "LUNAUSDT~2")
    first, second = panel.column("LUNAUSDT"), panel.column("LUNAUSDT~2")
    assert panel.last_valid[first] == 9
    assert panel.first_valid[second] == 30
    assert panel.bases == ("LUNA", "LUNA")


def test_short_gaps_do_not_split() -> None:
    days = np.array([0, 1, 2, 6, 7], dtype=np.int64)
    assert split_segments(days, max_gap=7) == [(0, 5)]


def test_exclusions_cover_stablecoins_leveraged_and_wrapped_tokens_but_not_lookalike_coins() -> (
    None
):
    bases = {"BTC", "ETH", "BTCUP", "ETHDOWN", "JUP", "USDC", "WBTC", "PAXG"}
    assert exclusion_reason("USDC", bases) == "stablecoin or fiat"
    assert exclusion_reason("BTCUP", bases) == "leveraged token"
    assert exclusion_reason("ETHDOWN", bases) == "leveraged token"
    assert exclusion_reason("WBTC", bases) == "wrapped or pegged copy"
    assert exclusion_reason("PAXG", bases) == "wrapped or pegged copy"
    assert exclusion_reason("JUP", bases) is None
    assert exclusion_reason("BTC", bases) is None


def test_universe_membership_ignores_everything_after_the_day() -> None:
    panel = random_walk_panel(12, 200, seed=3)
    rule = UniverseRule(top_n=5, window=20, min_history=30, min_quote_volume=0)
    t = 120
    before = PointInTimeUniverse(panel, rule).members(t)

    scrambled_qv = panel.quote_volume.copy()
    scrambled_qv[t + 1 :] = np.random.default_rng(9).uniform(
        1, 1e9, size=scrambled_qv[t + 1 :].shape
    )
    changed = type(panel)(
        days=panel.days,
        symbols=panel.symbols,
        open=panel.open,
        high=panel.high,
        low=panel.low,
        close=panel.close,
        quote_volume=scrambled_qv,
    )
    after = PointInTimeUniverse(changed, rule).members(t)

    assert before.sum() == 5
    assert (before == after).all()


def test_fresh_listings_wait_for_min_history() -> None:
    panel = random_walk_panel(3, 100, seed=4)
    rule = UniverseRule(top_n=3, window=10, min_history=50, min_quote_volume=0)
    universe = PointInTimeUniverse(panel, rule)
    assert universe.members(40).sum() == 0
    assert universe.members(60).sum() == 3

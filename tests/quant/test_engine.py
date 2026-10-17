"""The portfolio engine: timing, costs, delistings, tranches, and no peeking."""

from __future__ import annotations

import numpy as np
import pytest

from invest_ll.quant.engine import Costs, RunConfig, run
from invest_ll.quant.panel import Panel
from invest_ll.quant.strategies import HoldAsset, MomentumPortfolio, RotationTop1, TrendAsset
from invest_ll.quant.view import MarketView

from .builders import panel_from_closes, random_walk_panel

FREE = Costs(commission=0.0, slippage=0.0, impact=0.0, min_trade=0.0)


def test_orders_decided_at_a_close_fill_at_the_next_open() -> None:
    panel = panel_from_closes(
        {"AUSDT": [100, 100, 100, 100]},
        opens={"AUSDT": [100, 150, 100, 100]},
    )
    result = run(panel, HoldAsset("AUSDT"), FREE, RunConfig(initial_capital=1_000))
    # Decided at the close of day 0, bought at the open of day 1 (150), marked at the close (100).
    assert result.equity[0] == pytest.approx(1_000)
    assert result.equity[1] == pytest.approx(1_000 * 100 / 150)


def test_a_round_trip_pays_commission_and_slippage_twice() -> None:
    panel = panel_from_closes({"AUSDT": [100, 100, 100, 100, 100, 100]})
    costs = Costs(commission=0.001, slippage=0.0005, impact=0.0, min_trade=0.0)

    class InThenOut:
        name = "in then out"

        def weights(self, view: MarketView) -> np.ndarray:
            return np.array([1.0 if view.cursor < 2 else 0.0])

    result = run(panel, InThenOut(), costs, RunConfig(initial_capital=10_000, rebalance_every=1))
    rate = 0.0015
    bought = 10_000 / (1 + rate)
    assert result.equity[-1] == pytest.approx(bought * (1 - rate), rel=1e-9)
    assert result.costs.sum() == pytest.approx(10_000 - result.equity[-1], rel=1e-9)


def test_a_held_coin_that_stops_trading_is_sold_at_its_last_close() -> None:
    panel = panel_from_closes(
        {
            "DEADUSDT": [10, 10, 8, 4, None, None, None],
            "BTCUSDT": [1, 1, 1, 1, 1, 1, 1],
        }
    )
    result = run(
        panel,
        HoldAsset("DEADUSDT"),
        Costs(commission=0.0, slippage=0.0, impact=0.0, min_trade=0.0, delist_haircut=0.5),
        RunConfig(initial_capital=1_000),
    )
    # Bought at 10, last close 4, haircut 50%: 1000 * 0.4 * 0.5.
    assert result.equity[-1] == pytest.approx(200.0)
    assert any("DEADUSDT stopped trading" in n for n in result.notes)


def test_the_account_never_holds_more_than_it_has() -> None:
    panel = random_walk_panel(15, 300, seed=11)
    result = run(
        panel,
        MomentumPortfolio(lookbacks=(10, 20, 40), top_k=4, vol_lookback=20),
        Costs(commission=0.001, slippage=0.0005),
        RunConfig(initial_capital=10_000, rebalance_every=7, tranches=7),
    )
    assert (result.weights >= -1e-12).all()
    assert (result.weights.sum(axis=1) <= 1 + 1e-9).all()
    assert (result.equity > 0).all()


def test_one_tranche_is_the_plain_strategy() -> None:
    panel = random_walk_panel(5, 200, seed=5)
    a = run(panel, RotationTop1(20), FREE, RunConfig(initial_capital=1_000, rebalance_every=7))
    b = run(
        panel,
        RotationTop1(20),
        FREE,
        RunConfig(initial_capital=1_000, rebalance_every=7, tranches=1),
    )
    assert np.allclose(a.equity, b.equity)


def test_tranches_average_the_weekday_lottery() -> None:
    """Seven tranches end near the average of the seven single-weekday runs, not at an extreme."""
    panel = random_walk_panel(4, 400, seed=21)
    singles = [
        run(
            panel,
            TrendAsset("C0USDT", 20),
            FREE,
            RunConfig(initial_capital=1_000, rebalance_every=7, start=s),
        ).equity[-1]
        for s in range(7)
    ]
    tranched = run(
        panel,
        TrendAsset("C0USDT", 20),
        FREE,
        RunConfig(initial_capital=1_000, rebalance_every=7, tranches=7),
    ).equity[-1]
    assert min(singles) <= tranched <= max(singles)


def test_strategies_cannot_see_the_future() -> None:
    """Scrambling every row after the decision day leaves the decision unchanged."""
    panel = random_walk_panel(10, 220, seed=8)
    t = 150
    strategy = MomentumPortfolio(lookbacks=(10, 20, 40), top_k=3, vol_lookback=20)
    before = strategy.weights(MarketView(panel, t))

    rng = np.random.default_rng(1)
    future = panel.close.copy()
    future[t + 1 :] = rng.uniform(1, 1000, size=future[t + 1 :].shape)
    scrambled = Panel(
        days=panel.days,
        symbols=panel.symbols,
        open=future,
        high=future,
        low=future,
        close=future,
        quote_volume=panel.quote_volume,
    )
    after = strategy.weights(MarketView(scrambled, t))
    assert before is not None and after is not None
    assert np.allclose(before, after)


def test_momentum_portfolio_respects_the_position_cap_and_vol_target() -> None:
    panel = random_walk_panel(20, 200, seed=13)
    strategy = MomentumPortfolio(
        lookbacks=(10, 20), top_k=5, vol_lookback=20, max_weight=0.25, vol_target=0.2
    )
    w = strategy.weights(MarketView(panel, 150))
    assert w is not None
    assert w.max() <= 0.25 + 1e-12
    held = np.nonzero(w)[0]
    view = MarketView(panel, 150)
    cov = view.covariance(held, 20)
    vol = float(np.sqrt(w[held] @ cov @ w[held] * 365))
    assert vol <= 0.2 + 1e-9


def test_tax_is_paid_in_july_from_the_account() -> None:
    days_2024 = 366
    closes = [100.0] * 10 + [200.0] * (days_2024 - 10) + [200.0] * 200

    class SellInDecember:
        name = "sell in december"

        def weights(self, view: MarketView) -> np.ndarray:
            return np.array([1.0 if view.cursor < days_2024 - 5 else 0.0])

    panel = panel_from_closes({"AUSDT": closes})
    taxed = run(
        panel,
        SellInDecember(),
        FREE,
        RunConfig(initial_capital=10_000, rebalance_every=1, pay_tax=True),
    )
    untaxed = run(
        panel, SellInDecember(), FREE, RunConfig(initial_capital=10_000, rebalance_every=1)
    )
    # Bought at 100, sold at 200 in 2024: 10,000 gain -> 6,000*19% + 4,000*21% = 1,980 in July 2025.
    assert untaxed.equity[-1] == pytest.approx(20_000)
    assert taxed.equity[-1] == pytest.approx(20_000 - 1_980)
    assert taxed.taxes.sum() == pytest.approx(1_980)


def test_the_no_trade_band_skips_small_adjustments_but_never_an_exit() -> None:
    closes = {"AUSDT": [100.0] * 12, "BUSDT": [100.0] * 12}

    class Drift:
        name = "drift"

        def weights(self, view: MarketView) -> np.ndarray:
            if view.cursor < 3:
                return np.array([0.50, 0.40])
            if view.cursor < 6:
                return np.array([0.51, 0.40])  # 1 point: inside a 2-point band
            return np.array([0.51, 0.0])  # B leaves: an exit, never banded

    panel = panel_from_closes(closes)
    banded = run(
        panel,
        Drift(),
        FREE,
        RunConfig(initial_capital=10_000, rebalance_every=1, no_trade_band=0.02),
    )
    plain = run(panel, Drift(), FREE, RunConfig(initial_capital=10_000, rebalance_every=1))
    assert banded.trades < plain.trades
    assert banded.weights[-1][1] == 0.0


def test_on_decision_only_observes() -> None:
    """Every tranche decision is reported, in order, and the run is the same without it."""
    panel = random_walk_panel(3, 120, seed=5)
    config = RunConfig(initial_capital=1_000, rebalance_every=7, tranches=7)
    seen: list[tuple[int, int, float]] = []

    def note(tranche: int, row: int, target: np.ndarray) -> None:
        seen.append((tranche, row, float(target.sum())))

    watched = run(panel, TrendAsset("C0USDT", 20), FREE, config, on_decision=note)
    plain = run(panel, TrendAsset("C0USDT", 20), FREE, config)

    assert np.array_equal(watched.equity, plain.equity)
    assert watched.trades == plain.trades
    assert len(seen) == 119, "one decision a day (a tranche each), none on the last row"
    assert [t for t, _, _ in seen[:8]] == [0, 1, 2, 3, 4, 5, 6, 0]
    assert all(0.0 <= s <= 1.0 for _, _, s in seen)

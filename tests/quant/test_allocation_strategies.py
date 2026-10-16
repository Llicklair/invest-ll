"""Market filter, risk parity, cash sleeve and constant mixes."""

from __future__ import annotations

import numpy as np
import pytest

from invest_ll.quant.strategies import (
    CashSleeve,
    ConstantMix,
    MarketFilter,
    MomentumPortfolio,
    RiskParity,
)
from invest_ll.quant.view import MarketView

from .builders import panel_from_closes, random_walk_panel


def test_market_filter_goes_to_cash_when_the_market_trend_fails() -> None:
    n = 120
    falling_btc = [100.0 - 0.5 * i for i in range(n)]
    rising_alt = [10.0 + 0.1 * i for i in range(n)]
    panel = panel_from_closes({"BTCUSDT": falling_btc, "ALTUSDT": rising_alt})
    inner = MomentumPortfolio(lookbacks=(14, 30), top_k=2, vol_lookback=20, vol_target=None)
    view = MarketView(panel, n - 1)

    unfiltered = inner.weights(view)
    filtered = MarketFilter(inner, lookbacks=(14, 30)).weights(view)
    assert unfiltered is not None and unfiltered.sum() > 0
    assert filtered is not None and filtered.sum() == 0


def test_risk_parity_weights_are_inverse_to_volatility() -> None:
    rng = np.random.default_rng(2)
    calm = 100 * np.cumprod(1 + rng.normal(0, 0.005, 200))
    wild = 100 * np.cumprod(1 + rng.normal(0, 0.02, 200))
    panel = panel_from_closes({"CALM": calm.tolist(), "WILD": wild.tolist()})
    w = RiskParity(("CALM", "WILD"), vol_lookback=60).weights(MarketView(panel, 199))
    assert w is not None
    assert w.sum() == pytest.approx(1.0)
    assert w[0] / w[1] == pytest.approx(3.5, rel=0.35)


def test_trend_filter_keeps_a_falling_asset_budget_in_cash_and_the_sleeve_parks_it() -> None:
    up = [100.0 + i for i in range(300)]
    down = [400.0 - i for i in range(300)]
    cash = [100.0] * 300
    panel = panel_from_closes({"UP": up, "DOWN": down, "SHY": cash})
    parity = RiskParity(("UP", "DOWN"), vol_lookback=60, trend_lookbacks=(21, 63))
    view = MarketView(panel, 299)
    w = parity.weights(view)
    assert w is not None and w[1] == 0 and 0 < w[0] < 1
    sleeved = CashSleeve(parity, "SHY").weights(view)
    assert sleeved is not None
    assert sleeved.sum() == pytest.approx(1.0)
    assert sleeved[2] == pytest.approx(1 - w[0])


def test_constant_mix_restores_its_weights() -> None:
    panel = random_walk_panel(3, 50)
    mix = ConstantMix((("C0USDT", 0.6), ("C1USDT", 0.4)))
    w = mix.weights(MarketView(panel, 40))
    assert w is not None
    assert list(np.round(w, 6)) == [0.6, 0.4, 0.0]

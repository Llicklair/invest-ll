"""Tax book, metrics and the overfitting statistics."""

from __future__ import annotations

import numpy as np
import pytest

from invest_ll.quant.metrics import (
    deflated_sharpe,
    drawdown,
    longest_drawdown,
    per_period_sharpe,
    probabilistic_sharpe,
)
from invest_ll.quant.tax import FifoTaxBook, savings_tax
from invest_ll.quant.validation import bootstrap, probability_of_overfitting, walk_forward


def test_savings_scale() -> None:
    assert savings_tax(0) == 0
    assert savings_tax(6_000) == pytest.approx(1_140)
    assert savings_tax(10_000) == pytest.approx(1_140 + 840)
    assert savings_tax(400_000) == pytest.approx(
        1_140 + 44_000 * 0.21 + 150_000 * 0.23 + 100_000 * 0.27 + 100_000 * 0.30
    )


def test_fifo_matches_the_oldest_lot_first() -> None:
    book = FifoTaxBook()
    book.buy("BTC", 1.0, 100.0)
    book.buy("BTC", 1.0, 300.0)
    gain = book.sell("BTC", 1.0, 250.0, 2024)
    assert gain == pytest.approx(150.0)
    assert book.sell("BTC", 1.0, 250.0, 2024) == pytest.approx(-50.0)
    assert book.tax_for_year(2024) == pytest.approx(savings_tax(100.0))


def test_losses_carry_forward_for_four_years_only() -> None:
    book = FifoTaxBook()
    book.realised = {2020: -1_000.0, 2025: 1_000.0}
    assert book.tax_for_year(2020) == 0
    assert book.tax_for_year(2025) == pytest.approx(savings_tax(1_000.0))  # 2020 expired
    book = FifoTaxBook()
    book.realised = {2021: -1_000.0, 2025: 1_000.0}
    book.tax_for_year(2021)
    assert book.tax_for_year(2025) == 0  # 2021 still usable


def test_drawdown_is_measured_from_the_running_peak() -> None:
    eq = np.array([100, 120, 90, 130, 65, 130], dtype=float)
    dd = drawdown(eq)
    assert dd.min() == pytest.approx(-0.5)
    assert longest_drawdown(eq) == 1


def test_more_trials_make_the_same_sharpe_less_convincing() -> None:
    rng = np.random.default_rng(0)
    r = rng.normal(0.001, 0.01, 2000)
    few = np.array(
        [per_period_sharpe(rng.normal(0, 0.01, 2000)) for _ in range(3)] + [per_period_sharpe(r)]
    )
    many = np.array(
        [per_period_sharpe(rng.normal(0, 0.01, 2000)) for _ in range(300)] + [per_period_sharpe(r)]
    )
    assert deflated_sharpe(r, many) < deflated_sharpe(r, few) <= probabilistic_sharpe(r) + 1e-12


def test_pbo_is_high_for_noise_and_low_for_a_real_edge() -> None:
    rng = np.random.default_rng(42)
    noise = rng.normal(0, 0.01, size=(1600, 20))
    assert 0.3 <= probability_of_overfitting(noise, blocks=10).probability <= 0.7

    edge = noise.copy()
    edge[:, 3] += 0.003
    assert probability_of_overfitting(edge, blocks=10).probability < 0.05


def test_walk_forward_only_uses_past_years_to_choose() -> None:
    years = np.repeat(np.array([2020, 2021, 2022, 2023]), 100)
    rets = np.zeros((400, 2))
    rets[years <= 2021, 0] = 0.01  # config 0 good early
    rets[years <= 2021, 1] = -0.01
    rets[years >= 2022, 0] = -0.01  # then it flips
    rets[years >= 2022, 1] = 0.01
    rets += np.random.default_rng(1).normal(0, 1e-4, rets.shape)
    wf = walk_forward(["a", "b"], rets, years, min_train_years=2)
    assert [s.year for s in wf.steps] == [2022, 2023]
    assert wf.steps[0].chosen == "a"  # chosen on 2020-21, then it loses in 2022
    assert wf.steps[0].test_return < 0


def test_bootstrap_interval_contains_the_point_estimate() -> None:
    r = np.random.default_rng(3).normal(0.001, 0.02, 1500)
    cagr, sr = bootstrap(r, 365, samples=300)
    assert cagr.low < cagr.median < cagr.high
    assert sr.low < sr.median < sr.high

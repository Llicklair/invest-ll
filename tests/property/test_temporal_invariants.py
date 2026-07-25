"""T037 — invariantes temporales sobre series generadas (SC-008).

Los tests escritos a mano prueban los casos que se me ocurrieron. Estos prueban los que no.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from invest_ll.engine.backtest import run_backtest
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.engine.execution import ExitReason
from invest_ll.strategy.moving_average import MovingAverageCrossover

from ..fixtures.builders import series_from_closes

pytestmark = pytest.mark.property

D = Decimal
FRICCION = FrictionConfig(commission_rate=D("0.001"), slippage_rate=D("0.0005"))
RIESGO = RiskConfig(position_fraction=D("0.5"))

precios = st.lists(
    st.floats(min_value=1.0, max_value=10_000.0, allow_nan=False, allow_infinity=False),
    min_size=40,
    max_size=200,
)


@given(closes=precios)
@settings(max_examples=40, deadline=None)
def test_ninguna_orden_se_ejecuta_antes_de_su_senal(closes: list[float]) -> None:
    report = run_backtest(
        series_from_closes(closes),
        MovingAverageCrossover(short=3, long=10),
        initial_capital=D(10000),
        friction=FRICCION,
        risk=RIESGO,
    )
    for trade in report.trades:
        assert trade.entry_order.execution_timestamp > trade.entry_order.signal_timestamp
        if trade.exit_order is not None and trade.exit_reason is not ExitReason.END_OF_SERIES:
            assert trade.exit_order.execution_timestamp > trade.exit_order.signal_timestamp


@given(closes=precios)
@settings(max_examples=40, deadline=None)
def test_la_salida_nunca_precede_a_la_entrada(closes: list[float]) -> None:
    report = run_backtest(
        series_from_closes(closes),
        MovingAverageCrossover(short=3, long=10),
        initial_capital=D(10000),
        friction=FRICCION,
        risk=RIESGO,
    )
    for trade in report.trades:
        if trade.exit_order is not None:
            assert trade.exit_order.execution_timestamp >= trade.entry_order.execution_timestamp


@given(closes=precios)
@settings(max_examples=40, deadline=None)
def test_las_operaciones_no_se_solapan(closes: list[float]) -> None:
    """Una posición a la vez (v1): cada entrada ocurre tras cerrarse la anterior."""
    report = run_backtest(
        series_from_closes(closes),
        MovingAverageCrossover(short=3, long=10),
        initial_capital=D(10000),
        friction=FRICCION,
        risk=RIESGO,
    )
    for previa, siguiente in zip(report.trades, report.trades[1:], strict=False):
        assert previa.exit_order is not None
        assert siguiente.entry_order.execution_timestamp >= previa.exit_order.execution_timestamp

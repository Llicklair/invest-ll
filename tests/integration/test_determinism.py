"""T036 — reproducibilidad (FR-005, SC-006).

Un backtest que da resultados distintos en cada ejecución no permite comparar nada. Sin esto,
el Principio V no se sostiene.
"""

from __future__ import annotations

from decimal import Decimal

from invest_ll.engine.backtest import run_backtest
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.report.report import BacktestReport
from invest_ll.strategy.moving_average import MovingAverageCrossover

from ..fixtures.builders import series_from_closes, v_shape

D = Decimal
FRICCION = FrictionConfig(commission_rate=D("0.001"), slippage_rate=D("0.0005"))
RIESGO = RiskConfig(position_fraction=D("0.4"))


def ejecutar() -> BacktestReport:
    return run_backtest(
        series_from_closes(v_shape(120)),
        MovingAverageCrossover(short=4, long=12),
        initial_capital=D(10000),
        friction=FRICCION,
        risk=RIESGO,
    )


def test_dos_ejecuciones_dan_el_mismo_resultado() -> None:
    a, b = ejecutar(), ejecutar()
    assert a.net_result == b.net_result
    assert a.expectancy == b.expectancy
    assert a.max_drawdown == b.max_drawdown
    assert a.trade_count == b.trade_count
    assert a.total_costs == b.total_costs
    assert a.win_rate == b.win_rate


def test_el_registro_de_operaciones_es_identico() -> None:
    a, b = ejecutar(), ejecutar()
    assert len(a.trades) == len(b.trades)
    for ta, tb in zip(a.trades, b.trades, strict=True):
        assert ta.entry_order.execution_timestamp == tb.entry_order.execution_timestamp
        assert ta.entry_order.fill_price == tb.entry_order.fill_price
        assert ta.net_pnl == tb.net_pnl
        assert ta.exit_reason is tb.exit_reason


def test_el_texto_del_informe_es_identico() -> None:
    assert ejecutar().render() == ejecutar().render()


def test_diez_ejecuciones_convergen() -> None:
    """Si hubiera cualquier fuente de no-determinismo, diez pasadas la sacarían."""
    resultados = {ejecutar().net_result for _ in range(10)}
    assert len(resultados) == 1


def test_reordenar_la_construccion_no_cambia_el_resultado() -> None:
    """Misma serie construida dos veces por separado: el motor no arrastra estado global."""
    primero = ejecutar()
    _ = run_backtest(
        series_from_closes(v_shape(60)),
        MovingAverageCrossover(short=3, long=9),
        initial_capital=D(5000),
        friction=FRICCION,
        risk=RIESGO,
    )
    segundo = ejecutar()
    assert primero.net_result == segundo.net_result

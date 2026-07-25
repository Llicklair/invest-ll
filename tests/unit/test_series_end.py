"""T038 — bordes del final de la serie (edge cases de la spec)."""

from __future__ import annotations

from decimal import Decimal

from invest_ll.engine.backtest import run_backtest
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.engine.execution import ExitReason

from ..fixtures.builders import ramp, series_from_closes
from .helpers_strategies import EntraYMantiene

D = Decimal
SIN_FRICCION = FrictionConfig(commission_rate=D(0), slippage_rate=D(0))
TODO = RiskConfig(position_fraction=D(1))


def test_posicion_abierta_al_final_se_liquida_y_se_marca() -> None:
    """No se puede ignorar: dejaría fuera una ganancia o pérdida real."""
    report = run_backtest(
        series_from_closes(ramp(20)),
        EntraYMantiene(),
        initial_capital=D(10000),
        friction=SIN_FRICCION,
        risk=TODO,
    )
    assert report.trade_count == 1
    assert report.trades[0].exit_reason is ExitReason.END_OF_SERIES


def test_la_liquidacion_final_se_avisa_en_el_informe() -> None:
    """El operador debe saber que ese resultado no lo decidió la estrategia."""
    report = run_backtest(
        series_from_closes(ramp(20)),
        EntraYMantiene(),
        initial_capital=D(10000),
        friction=SIN_FRICCION,
        risk=TODO,
    )
    texto = report.render().lower()
    assert "abiertas al agotarse" in texto


def test_los_cierres_se_desglosan_por_motivo() -> None:
    report = run_backtest(
        series_from_closes(ramp(20)),
        EntraYMantiene(),
        initial_capital=D(10000),
        friction=SIN_FRICCION,
        risk=TODO,
    )
    desglose = report.exits_by_reason()
    assert desglose[ExitReason.END_OF_SERIES] == 1
    assert desglose[ExitReason.SIGNAL] == 0


def test_serie_de_un_solo_periodo_no_produce_operaciones() -> None:
    """No hay periodo siguiente donde ejecutar nada."""
    report = run_backtest(
        series_from_closes([100.0]),
        EntraYMantiene(),
        initial_capital=D(10000),
        friction=SIN_FRICCION,
        risk=TODO,
    )
    assert report.trade_count == 0
    assert not report.conclusive


def test_serie_mas_corta_que_la_estrategia_no_opera() -> None:
    """Sin histórico suficiente para las medias, no se opera a ciegas."""
    from invest_ll.strategy.moving_average import MovingAverageCrossover

    report = run_backtest(
        series_from_closes(ramp(5)),
        MovingAverageCrossover(short=3, long=20),
        initial_capital=D(10000),
        friction=SIN_FRICCION,
        risk=TODO,
    )
    assert report.trade_count == 0

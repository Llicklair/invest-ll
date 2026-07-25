"""T042 — estrategias intercambiables y comparables (SC-005, Principio V)."""

from __future__ import annotations

from decimal import Decimal

from invest_ll.engine.backtest import run_backtest
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.report.report import BacktestReport
from invest_ll.strategy.breakout import BreakoutHighs
from invest_ll.strategy.moving_average import MovingAverageCrossover
from invest_ll.strategy.protocol import Strategy

from ..fixtures.builders import series_from_closes, v_shape

D = Decimal
FRICCION = FrictionConfig(commission_rate=D("0.001"), slippage_rate=D("0.0005"))
RIESGO = RiskConfig(position_fraction=D("0.5"))
PRECIOS = v_shape(150)


def evaluar(strategy: Strategy) -> BacktestReport:
    return run_backtest(
        series_from_closes(PRECIOS),
        strategy,
        initial_capital=D(10000),
        friction=FRICCION,
        risk=RIESGO,
    )


def test_ambas_estrategias_cumplen_el_protocolo() -> None:
    assert isinstance(MovingAverageCrossover(), Strategy)
    assert isinstance(BreakoutHighs(), Strategy)


def test_los_informes_tienen_la_misma_estructura() -> None:
    """Comparar exige la misma vara: mismos campos, mismo significado."""
    a = evaluar(MovingAverageCrossover(short=5, long=20))
    b = evaluar(BreakoutHighs(lookback=20))
    assert type(a) is type(b)
    campos_a = set(BacktestReport.__dataclass_fields__)
    assert campos_a == set(type(b).__dataclass_fields__)


def test_se_miden_sobre_los_mismos_datos_y_configuracion() -> None:
    a = evaluar(MovingAverageCrossover(short=5, long=20))
    b = evaluar(BreakoutHighs(lookback=20))
    assert a.friction == b.friction
    assert a.risk == b.risk
    assert a.symbol == b.symbol


def test_la_segunda_estrategia_no_requirio_tocar_el_motor() -> None:
    """SC-005: el motor solo conoce el protocolo, no las estrategias concretas."""
    import invest_ll.engine.backtest as motor

    fuente = motor.__doc__ or ""
    codigo = motor.run_backtest.__code__
    nombres = set(codigo.co_names) | set(fuente.split())
    for prohibido in ("MovingAverageCrossover", "BreakoutHighs", "moving_average", "breakout"):
        assert prohibido not in nombres


def test_ambas_producen_operaciones_reales() -> None:
    assert evaluar(MovingAverageCrossover(short=5, long=20)).trade_count >= 1
    assert evaluar(BreakoutHighs(lookback=10)).trade_count >= 1


def test_un_stub_de_test_tambien_sirve_como_estrategia() -> None:
    """Si un stub trivial no valiera, envolver un modelo de IA tampoco valdría."""
    from ..unit.helpers_strategies import AlternaCadaDosPeriodos

    report = evaluar(AlternaCadaDosPeriodos())
    assert report.trade_count >= 1

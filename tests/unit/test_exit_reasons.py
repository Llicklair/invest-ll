"""T049 — el informe distingue por qué se cerró cada operación (FR-031).

Importa porque no es lo mismo una estrategia que cierra cuando quiere que una a la que el stop
la saca a rastras: el mismo resultado neto cuenta dos historias distintas.
"""

from __future__ import annotations

from decimal import Decimal

from invest_ll.engine.backtest import run_backtest
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.engine.execution import ExitReason

from ..fixtures.builders import ramp, series_from_closes
from .helpers_strategies import AlternaCadaDosPeriodos, EntraYMantiene
from .test_protective_exits import EntraConProteccion, serie

D = Decimal
SIN_FRICCION = FrictionConfig(commission_rate=D(0), slippage_rate=D(0))
TODO = RiskConfig(position_fraction=D(1))


def test_cierre_por_senal_se_etiqueta_como_tal() -> None:
    report = run_backtest(
        series_from_closes(ramp(40)),
        AlternaCadaDosPeriodos(),
        initial_capital=D(100000),
        friction=SIN_FRICCION,
        risk=TODO,
    )
    desglose = report.exits_by_reason()
    assert desglose[ExitReason.SIGNAL] >= 1


def test_cierre_por_stop_se_etiqueta_como_tal() -> None:
    velas = [
        (100.0, 100.0, 100.0, 100.0),
        (100.0, 100.0, 100.0, 100.0),
        (100.0, 102.0, 100.0, 101.0),
        (101.0, 101.0, 85.0, 88.0),
    ]
    report = run_backtest(
        serie(velas),
        EntraConProteccion(),
        initial_capital=D(10000),
        friction=SIN_FRICCION,
        risk=TODO,
    )
    assert report.exits_by_reason()[ExitReason.STOP_LOSS] == 1


def test_cierre_por_take_se_etiqueta_como_tal() -> None:
    velas = [
        (100.0, 100.0, 100.0, 100.0),
        (100.0, 100.0, 100.0, 100.0),
        (100.0, 102.0, 100.0, 101.0),
        (101.0, 125.0, 101.0, 124.0),
    ]
    report = run_backtest(
        serie(velas),
        EntraConProteccion(),
        initial_capital=D(10000),
        friction=SIN_FRICCION,
        risk=TODO,
    )
    assert report.exits_by_reason()[ExitReason.TAKE_PROFIT] == 1


def test_liquidacion_final_se_etiqueta_aparte() -> None:
    report = run_backtest(
        series_from_closes(ramp(20)),
        EntraYMantiene(),
        initial_capital=D(10000),
        friction=SIN_FRICCION,
        risk=TODO,
    )
    assert report.exits_by_reason()[ExitReason.END_OF_SERIES] == 1


def test_el_desglose_cubre_todas_las_operaciones() -> None:
    report = run_backtest(
        series_from_closes(ramp(40)),
        AlternaCadaDosPeriodos(),
        initial_capital=D(100000),
        friction=SIN_FRICCION,
        risk=TODO,
    )
    assert sum(report.exits_by_reason().values()) == report.trade_count

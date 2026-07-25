"""T048 — salidas de protección (FR-028..FR-030).

Con datos en velas no se conoce el recorrido del precio *dentro* del periodo. Toda ambigüedad se
resuelve en contra: es la única forma de que el backtest no se mienta a su favor.
"""

from __future__ import annotations

from decimal import Decimal

from invest_ll.data.bar import Interval
from invest_ll.data.calendars import Continuous24x7
from invest_ll.data.series import PriceSeries
from invest_ll.engine.backtest import run_backtest
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.engine.execution import ExitReason
from invest_ll.engine.view import MarketView
from invest_ll.report.report import BacktestReport
from invest_ll.strategy.protocol import Signal, SignalKind, Strategy

from ..fixtures.builders import ORIGIN, bar_at

D = Decimal
SIN_FRICCION = FrictionConfig(commission_rate=D(0), slippage_rate=D(0))
TODO = RiskConfig(position_fraction=D(1))


class EntraConProteccion:
    """Entra en el segundo periodo con stop en 90 y take en 120."""

    def __init__(self, stop: float | None = 90.0, take: float | None = 120.0) -> None:
        self._stop = stop
        self._take = take

    def decide(self, view: MarketView) -> Signal | None:
        if len(view) == 2:
            return Signal(kind=SignalKind.ENTER_LONG, stop_loss=self._stop, take_profit=self._take)
        return None


def serie(velas: list[tuple[float, float, float, float]]) -> PriceSeries:
    """Construye una serie a partir de tuplas (open, high, low, close)."""
    bars = tuple(
        bar_at(
            ORIGIN + Interval.DAY_1.duration * i,
            close,
            open_=o,
            high=h,
            low=lo,
        )
        for i, (o, h, lo, close) in enumerate(velas)
    )
    return PriceSeries(symbol="TEST", interval=Interval.DAY_1, calendar=Continuous24x7(), bars=bars)


def ejecutar(
    velas: list[tuple[float, float, float, float]], strategy: Strategy | None = None
) -> BacktestReport:
    return run_backtest(
        serie(velas),
        strategy or EntraConProteccion(),
        initial_capital=D(10000),
        friction=SIN_FRICCION,
        risk=TODO,
    )


def test_el_stop_se_ejecuta_cuando_el_precio_lo_toca() -> None:
    velas = [
        (100.0, 100.0, 100.0, 100.0),
        (100.0, 100.0, 100.0, 100.0),
        (100.0, 102.0, 100.0, 101.0),  # entrada aquí, a 100
        (101.0, 101.0, 85.0, 88.0),  # el mínimo atraviesa el stop de 90
    ]
    report = ejecutar(velas)
    assert report.trade_count == 1
    assert report.trades[0].exit_reason is ExitReason.STOP_LOSS
    assert report.trades[0].exit_order is not None
    assert report.trades[0].exit_order.fill_price == D(90)


def test_el_take_profit_se_ejecuta_cuando_el_precio_lo_toca() -> None:
    velas = [
        (100.0, 100.0, 100.0, 100.0),
        (100.0, 100.0, 100.0, 100.0),
        (100.0, 102.0, 100.0, 101.0),
        (101.0, 125.0, 101.0, 124.0),  # el máximo supera el take de 120
    ]
    report = ejecutar(velas)
    assert report.trades[0].exit_reason is ExitReason.TAKE_PROFIT
    assert report.trades[0].exit_order is not None
    assert report.trades[0].exit_order.fill_price == D(120)


def test_si_ambos_caben_en_la_vela_se_asume_el_stop() -> None:
    """FR-029: la convención pesimista.

    Con datos en velas no se sabe si primero se tocó el stop o el take. Asumir el take sería
    quedarse con la versión optimista de una historia que no conocemos.
    """
    velas = [
        (100.0, 100.0, 100.0, 100.0),
        (100.0, 100.0, 100.0, 100.0),
        (100.0, 102.0, 100.0, 101.0),
        (101.0, 130.0, 85.0, 100.0),  # toca stop (90) Y take (120) en la misma vela
    ]
    report = ejecutar(velas)
    assert report.trades[0].exit_reason is ExitReason.STOP_LOSS
    assert report.trades[0].net_pnl < 0


def test_una_apertura_que_atraviesa_el_stop_ejecuta_al_precio_real() -> None:
    """FR-030: si abre por debajo del stop, no se cobra el nivel del stop sino la apertura.

    Es exactamente lo que ocurre con un hueco a la baja: el stop no protege del salto.
    """
    velas = [
        (100.0, 100.0, 100.0, 100.0),
        (100.0, 100.0, 100.0, 100.0),
        (100.0, 102.0, 100.0, 101.0),
        (70.0, 75.0, 65.0, 72.0),  # abre en 70, muy por debajo del stop de 90
    ]
    report = ejecutar(velas)
    trade = report.trades[0]
    assert trade.exit_reason is ExitReason.STOP_LOSS
    assert trade.exit_order is not None
    assert trade.exit_order.fill_price == D(70), "el stop no puede fingir que protegió del hueco"


def test_sin_niveles_no_hay_salida_de_proteccion() -> None:
    velas = [
        (100.0, 100.0, 100.0, 100.0),
        (100.0, 100.0, 100.0, 100.0),
        (100.0, 102.0, 100.0, 101.0),
        (101.0, 130.0, 50.0, 60.0),
    ]
    report = ejecutar(velas, EntraConProteccion(stop=None, take=None))
    assert report.trades[0].exit_reason is ExitReason.END_OF_SERIES


def test_el_precio_que_no_alcanza_el_nivel_no_dispara() -> None:
    velas = [
        (100.0, 100.0, 100.0, 100.0),
        (100.0, 100.0, 100.0, 100.0),
        (100.0, 102.0, 100.0, 101.0),
        (101.0, 119.0, 91.0, 110.0),  # se queda dentro de [90, 120]
    ]
    report = ejecutar(velas)
    assert report.trades[0].exit_reason is ExitReason.END_OF_SERIES

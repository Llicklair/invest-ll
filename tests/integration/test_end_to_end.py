"""T026 — validación de extremo a extremo (US1).

El informe debe coincidir con un resultado calculado a mano. Si esta prueba pasa, el motor mide
lo que dice medir.
"""

from __future__ import annotations

from decimal import Decimal

from invest_ll.engine.backtest import run_backtest
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.engine.view import MarketView
from invest_ll.strategy.moving_average import MovingAverageCrossover
from invest_ll.strategy.protocol import Signal, SignalKind

from ..fixtures.builders import series_from_closes, v_shape

D = Decimal
SIN_FRICCION = FrictionConfig(commission_rate=D(0), slippage_rate=D(0))
TODO = RiskConfig(position_fraction=D(1))


class EntraEnTresSaleEnCinco:
    """Una sola operación, con precios de ejecución conocidos de antemano."""

    def decide(self, view: MarketView) -> Signal | None:
        if len(view) == 3:
            return Signal(kind=SignalKind.ENTER_LONG)
        if len(view) == 5:
            return Signal(kind=SignalKind.EXIT)
        return None


def test_resultado_coincide_con_el_calculo_manual() -> None:
    """Cálculo a mano:

    Cierres: 100, 100, 100, 110, 120, 130, 130.
    - Señal de entrada tras la vela 2 (índice 2) → ejecuta en la apertura de la 3 = 110.
    - Con 1100 de capital y fracción 1: 1100 / 110 = 10 unidades.
    - Señal de salida tras la vela 4 → ejecuta en la apertura de la 5 = 130.
    - Resultado bruto: (130 - 110) x 10 = 200. Sin fricción, neto = 200.
    """
    serie = series_from_closes([100.0, 100.0, 100.0, 110.0, 120.0, 130.0, 130.0])
    report = run_backtest(
        serie,
        EntraEnTresSaleEnCinco(),
        initial_capital=D(1100),
        friction=SIN_FRICCION,
        risk=TODO,
    )

    assert report.trade_count == 1
    trade = report.trades[0]
    assert trade.entry_order.fill_price == D(110)
    assert trade.exit_order is not None
    assert trade.exit_order.fill_price == D(130)
    assert trade.entry_order.filled_quantity == D(10)
    assert trade.net_pnl == D(200)
    assert report.net_result == D(200)
    assert report.expectancy == D(200)
    assert report.win_rate == 1.0


def test_las_seis_metricas_estan_siempre_presentes() -> None:
    """SC-002."""
    serie = series_from_closes(v_shape(60))
    report = run_backtest(
        serie,
        MovingAverageCrossover(short=3, long=10),
        initial_capital=D(10000),
        friction=FrictionConfig(commission_rate=D("0.001"), slippage_rate=D("0.0005")),
        risk=RiskConfig(position_fraction=D("0.5")),
    )
    for metrica in (
        report.net_result,
        report.expectancy,
        report.max_drawdown,
        report.trade_count,
        report.total_costs,
        report.win_rate,
    ):
        assert metrica is not None


def test_la_suma_de_operaciones_reconstruye_el_resultado() -> None:
    """SC-007: cualquier cifra del informe se puede auditar desde el registro."""
    serie = series_from_closes(v_shape(80))
    report = run_backtest(
        serie,
        MovingAverageCrossover(short=3, long=8),
        initial_capital=D(10000),
        friction=FrictionConfig(commission_rate=D("0.001"), slippage_rate=D(0)),
        risk=RiskConfig(position_fraction=D("0.5")),
    )
    assert report.net_result == sum((t.net_pnl for t in report.trades), start=D(0))


def test_el_cruce_de_medias_opera_en_una_v() -> None:
    """FR-019: la estrategia de referencia debe producir operaciones reales."""
    serie = series_from_closes(v_shape(100))
    report = run_backtest(
        serie,
        MovingAverageCrossover(short=5, long=20),
        initial_capital=D(10000),
        friction=SIN_FRICCION,
        risk=TODO,
    )
    assert report.trade_count >= 1

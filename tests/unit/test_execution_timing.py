"""T021 — temporización de la ejecución (FR-024, FR-025, SC-008).

La comprobación que impide el look-ahead sutil: decidir viendo el cierre y fingir que operaste
a ese mismo precio.
"""

from __future__ import annotations

from decimal import Decimal

from invest_ll.engine.backtest import run_backtest
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.engine.view import MarketView
from invest_ll.strategy.protocol import Signal, SignalKind

from ..fixtures.builders import series_from_closes

D = Decimal
SIN_FRICCION = FrictionConfig(commission_rate=D(0), slippage_rate=D(0))
RIESGO = RiskConfig(position_fraction=D(1))


class EntraEnElTercerPeriodo:
    """Emite una única señal de entrada mirando la vela de índice 2."""

    def decide(self, view: MarketView) -> Signal | None:
        if len(view) == 3:
            return Signal(kind=SignalKind.ENTER_LONG)
        return None


def test_la_orden_se_ejecuta_en_la_apertura_siguiente() -> None:
    # Cierres planos salvo un salto en el periodo 3: si el motor ejecutara al cierre del
    # periodo 2 el precio sería 100; ejecutando en la apertura del 3 debe ser 150.
    serie = series_from_closes([100.0, 100.0, 100.0, 150.0, 150.0, 150.0])
    report = run_backtest(
        serie,
        EntraEnElTercerPeriodo(),
        initial_capital=D(10000),
        friction=SIN_FRICCION,
        risk=RIESGO,
    )
    entrada = report.trades[0].entry_order
    assert entrada.fill_price == D(150), "se ejecutó al cierre de la vela de la señal"


def test_execution_timestamp_es_posterior_a_signal_timestamp() -> None:
    """Toda orden nacida de una señal se ejecuta después de esa señal.

    Se excluye la liquidación por fin de serie: no es una orden que la estrategia pidiera, sino
    la valoración de la posición abierta al último cierre conocido. No hay periodo siguiente
    donde ejecutarla, y fingir uno sería inventar datos.
    """
    from invest_ll.engine.execution import ExitReason

    serie = series_from_closes([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    report = run_backtest(
        serie,
        EntraEnElTercerPeriodo(),
        initial_capital=D(10000),
        friction=SIN_FRICCION,
        risk=RIESGO,
    )
    assert report.trade_count > 0
    for trade in report.trades:
        assert trade.entry_order.execution_timestamp > trade.entry_order.signal_timestamp
        if trade.exit_order is not None and trade.exit_reason is not ExitReason.END_OF_SERIES:
            assert trade.exit_order.execution_timestamp > trade.exit_order.signal_timestamp


def test_todas_las_ordenes_cumplen_la_regla() -> None:
    """SC-008 sobre un backtest con muchas operaciones."""
    from invest_ll.engine.execution import ExitReason

    from .helpers_strategies import AlternaCadaDosPeriodos

    serie = series_from_closes([100.0 + i for i in range(40)])
    report = run_backtest(
        serie,
        AlternaCadaDosPeriodos(),
        initial_capital=D(100000),
        friction=SIN_FRICCION,
        risk=RIESGO,
    )
    assert report.trade_count > 0
    cerradas_por_fin = {
        id(t.exit_order) for t in report.trades if t.exit_reason is ExitReason.END_OF_SERIES
    }
    for orden in report.all_orders():
        if id(orden) in cerradas_por_fin:
            continue
        assert orden.execution_timestamp > orden.signal_timestamp


def test_senal_en_el_ultimo_periodo_no_crea_operacion_fantasma() -> None:
    """No hay apertura siguiente donde ejecutar: la orden se rechaza."""

    class EntraAlFinal:
        def decide(self, view: MarketView) -> Signal | None:
            if len(view) == 5:
                return Signal(kind=SignalKind.ENTER_LONG)
            return None

    serie = series_from_closes([100.0, 101.0, 102.0, 103.0, 104.0])
    report = run_backtest(
        serie, EntraAlFinal(), initial_capital=D(10000), friction=SIN_FRICCION, risk=RIESGO
    )
    assert report.trade_count == 0

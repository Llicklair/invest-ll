"""T025 — capital y fricción aplicada (FR-007, FR-010, FR-026)."""

from __future__ import annotations

from decimal import Decimal

from invest_ll.engine.backtest import run_backtest
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.engine.execution import OrderStatus

from ..fixtures.builders import series_from_closes
from .helpers_strategies import AlternaCadaDosPeriodos, EntraYMantiene, NuncaOpera

D = Decimal
SIN_FRICCION = FrictionConfig(commission_rate=D(0), slippage_rate=D(0))
CON_FRICCION = FrictionConfig(commission_rate=D("0.001"), slippage_rate=D("0.0005"))
TODO_EL_CAPITAL = RiskConfig(position_fraction=D(1))
UN_QUINTO = RiskConfig(position_fraction=D("0.2"))

PRECIOS = [100.0 + i for i in range(30)]


def test_sin_senales_no_hay_operaciones() -> None:
    report = run_backtest(
        series_from_closes(PRECIOS),
        NuncaOpera(),
        initial_capital=D(10000),
        friction=CON_FRICCION,
        risk=UN_QUINTO,
    )
    assert report.trade_count == 0
    assert report.net_result == D(0)
    assert not report.conclusive


def test_la_fraccion_limita_el_capital_comprometido() -> None:
    """FR-026: con una quinta parte, la entrada no puede usar más de eso."""
    report = run_backtest(
        series_from_closes(PRECIOS),
        EntraYMantiene(),
        initial_capital=D(10000),
        friction=SIN_FRICCION,
        risk=UN_QUINTO,
    )
    entrada = report.trades[0].entry_order
    comprometido = entrada.filled_quantity * entrada.fill_price
    assert comprometido <= D(10000) * D("0.2") + D("0.01")


def test_capital_insuficiente_rechaza_la_orden_sin_reventar() -> None:
    """FR-010: se registra como rechazada; el backtest continúa, como en un mercado real.

    El capital debe quedar por debajo del lote mínimo (1e-8 unidades): los activos son
    fraccionables, así que con 0,01 € y un precio de 100 sí se puede comprar una diezmilésima.
    """
    serie = series_from_closes(PRECIOS)
    report = run_backtest(
        serie,
        AlternaCadaDosPeriodos(),
        initial_capital=D("0.0000001"),  # ni un lote mínimo a precio 100
        friction=CON_FRICCION,
        risk=TODO_EL_CAPITAL,
    )
    assert report.trade_count == 0
    rechazadas = [o for o in report.all_orders() if o.status is OrderStatus.REJECTED]
    assert rechazadas
    assert rechazadas[0].rejection_reason is not None


def test_la_caja_nunca_queda_negativa() -> None:
    report = run_backtest(
        series_from_closes(PRECIOS),
        AlternaCadaDosPeriodos(),
        initial_capital=D(10000),
        friction=CON_FRICCION,
        risk=TODO_EL_CAPITAL,
    )
    assert report.final_cash >= 0


def test_la_friccion_reduce_el_resultado() -> None:
    """Mismo mercado y misma estrategia: la única diferencia son los costes."""
    serie = series_from_closes(PRECIOS)

    limpio = run_backtest(
        serie,
        AlternaCadaDosPeriodos(),
        initial_capital=D(10000),
        friction=SIN_FRICCION,
        risk=TODO_EL_CAPITAL,
    )
    con_costes = run_backtest(
        serie,
        AlternaCadaDosPeriodos(),
        initial_capital=D(10000),
        friction=CON_FRICCION,
        risk=TODO_EL_CAPITAL,
    )

    assert con_costes.total_costs > 0
    assert con_costes.net_result < limpio.net_result


def test_los_costes_se_contabilizan_por_operacion() -> None:
    report = run_backtest(
        series_from_closes(PRECIOS),
        AlternaCadaDosPeriodos(),
        initial_capital=D(10000),
        friction=CON_FRICCION,
        risk=TODO_EL_CAPITAL,
    )
    assert report.total_costs == sum((t.costs for t in report.trades), start=D(0))

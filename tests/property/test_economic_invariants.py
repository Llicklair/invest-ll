"""T053 — invariantes económicos sobre series generadas (SC-007).

Propiedades que deben cumplirse pase lo que pase con los precios. Si alguna se rompe, el informe
está mintiendo aunque todos los tests escritos a mano pasen.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from invest_ll.engine.backtest import run_backtest
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.report.report import BacktestReport
from invest_ll.strategy.moving_average import MovingAverageCrossover

from ..fixtures.builders import series_from_closes

pytestmark = pytest.mark.property

D = Decimal
FRICCION = FrictionConfig(commission_rate=D("0.001"), slippage_rate=D("0.0005"))
RIESGO = RiskConfig(position_fraction=D("0.5"))

precios = st.lists(
    st.floats(min_value=0.01, max_value=100_000.0, allow_nan=False, allow_infinity=False),
    min_size=30,
    max_size=150,
)


def evaluar(closes: list[float]) -> BacktestReport:
    return run_backtest(
        series_from_closes(closes),
        MovingAverageCrossover(short=3, long=10),
        initial_capital=D(10000),
        friction=FRICCION,
        risk=RIESGO,
    )


@given(closes=precios)
@settings(max_examples=50, deadline=None)
def test_la_caja_nunca_queda_negativa(closes: list[float]) -> None:
    """No hay apalancamiento en v1: no se puede gastar dinero que no se tiene."""
    assert evaluar(closes).final_cash >= 0


@given(closes=precios)
@settings(max_examples=50, deadline=None)
def test_el_drawdown_nunca_es_positivo(closes: list[float]) -> None:
    """Una caída no puede ser una ganancia. Si sale positivo, el signo está invertido."""
    assert evaluar(closes).max_drawdown <= 0


@given(closes=precios)
@settings(max_examples=50, deadline=None)
def test_la_suma_de_operaciones_reconstruye_el_resultado(closes: list[float]) -> None:
    """SC-007: cualquier cifra del informe se puede auditar desde el registro."""
    report = evaluar(closes)
    assert report.net_result == sum((t.net_pnl for t in report.trades), start=D(0))


@given(closes=precios)
@settings(max_examples=50, deadline=None)
def test_los_costes_nunca_son_negativos(closes: list[float]) -> None:
    """Operar siempre cuesta dinero. Un coste negativo sería un ingreso inventado."""
    report = evaluar(closes)
    assert report.total_costs >= 0
    for trade in report.trades:
        assert trade.costs >= 0


@given(closes=precios)
@settings(max_examples=50, deadline=None)
def test_la_expectancy_es_el_resultado_entre_operaciones(closes: list[float]) -> None:
    report = evaluar(closes)
    if report.trade_count:
        assert report.expectancy == report.net_result / report.trade_count
    else:
        assert report.expectancy == 0


@given(closes=precios)
@settings(max_examples=50, deadline=None)
def test_el_win_rate_esta_entre_cero_y_uno(closes: list[float]) -> None:
    assert 0.0 <= evaluar(closes).win_rate <= 1.0


@given(closes=precios)
@settings(max_examples=50, deadline=None)
def test_pocas_operaciones_nunca_concluyen(closes: list[float]) -> None:
    """FR-013 sin excepciones, gane lo que gane."""
    report = evaluar(closes)
    if report.trade_count < report.min_trades:
        assert not report.conclusive
        assert report.inconclusive_reason is not None


@given(closes=precios)
@settings(max_examples=50, deadline=None)
def test_el_informe_siempre_se_puede_imprimir(closes: list[float]) -> None:
    """Un veredicto que revienta al mostrarlo no sirve de nada.

    Se codifica a cp1252 a propósito: es lo que usa la consola de Windows por defecto.
    """
    texto = evaluar(closes).render()
    texto.encode("cp1252")

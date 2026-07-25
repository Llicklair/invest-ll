"""T047 — cuánto pesa la fricción (US4, FR-008).

La pregunta que responde: ¿mi estrategia sobrevive a los costes reales, o solo gana en un mercado
sin comisiones que no existe?
"""

from __future__ import annotations

from decimal import Decimal

from invest_ll.engine.backtest import run_backtest
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.report.report import BacktestReport

from ..fixtures.builders import series_from_closes, v_shape
from .helpers_strategies import AlternaCadaDosPeriodos

D = Decimal
RIESGO = RiskConfig(position_fraction=D("0.5"))
PRECIOS = v_shape(120)


def evaluar(commission: str, slippage: str = "0") -> BacktestReport:
    return run_backtest(
        series_from_closes(PRECIOS),
        AlternaCadaDosPeriodos(),
        initial_capital=D(10000),
        friction=FrictionConfig(commission_rate=D(commission), slippage_rate=D(slippage)),
        risk=RIESGO,
    )


def test_mas_comision_da_peor_resultado() -> None:
    barato = evaluar("0.0001")
    caro = evaluar("0.01")
    assert caro.net_result < barato.net_result
    assert caro.total_costs > barato.total_costs


def test_el_coste_escala_con_el_numero_de_operaciones() -> None:
    """Cada operación paga: una estrategia que opera mucho paga mucho."""
    report = evaluar("0.001")
    assert report.trade_count > 0
    coste_medio = report.total_costs / report.trade_count
    assert coste_medio > 0


def test_el_slippage_tambien_resta() -> None:
    sin_slippage = evaluar("0.001", "0")
    con_slippage = evaluar("0.001", "0.005")
    assert con_slippage.net_result < sin_slippage.net_result


def test_los_parametros_aplicados_constan_en_el_informe() -> None:
    report = evaluar("0.0025", "0.001")
    texto = report.render()
    assert "0.0025" in texto
    assert "0.001" in texto


def test_el_slippage_siempre_juega_en_contra() -> None:
    """Comprar más caro y vender más barato. Nunca al revés."""
    from invest_ll.engine.execution import OrderSide, apply_slippage

    precio = D(100)
    rate = D("0.01")
    assert apply_slippage(precio, OrderSide.BUY, rate) > precio
    assert apply_slippage(precio, OrderSide.SELL, rate) < precio


def test_una_estrategia_rentable_sin_costes_puede_perder_con_ellos() -> None:
    """El caso que justifica el Principio IV.

    Si la fricción no se modela, una estrategia que opera mucho parece rentable y no lo es.
    """
    limpio = evaluar("0")
    caro = evaluar("0.02")
    assert limpio.net_result > caro.net_result
    assert caro.total_costs > 0

"""Comparación contra comprar y mantener.

La pregunta que decide si una estrategia justifica su existencia: ¿bate a no hacer nada? Si no lo
hace, todo su riesgo y todas sus comisiones han sido para nada, por bonito que sea su win rate.

El listón se calcula con la **misma fricción** que la estrategia — comprar y mantener también paga
una comisión de entrada y otra de salida — y se reporta también su drawdown, porque ganar menos
sufriendo mucho menos sí es un resultado legítimo.
"""

from __future__ import annotations

from decimal import Decimal

from invest_ll.engine.benchmark import buy_and_hold
from invest_ll.engine.config import FrictionConfig, RiskConfig

from ..fixtures.builders import ramp, series_from_closes, v_shape

D = Decimal
SIN_FRICCION = FrictionConfig(commission_rate=D(0), slippage_rate=D(0))
CON_FRICCION = FrictionConfig(commission_rate=D("0.001"), slippage_rate=D("0.0005"))


class TestCalculo:
    def test_un_mercado_que_sube_da_ganancia(self) -> None:
        """Entra en la APERTURA del segundo periodo, no en el primero.

        Serie 100 / 105 / 110 con 1.000 de capital: compra a 105 (no a 100) y vende a 110.
        1000 / 105 = 9,52380952 unidades, que ganan 5 cada una = 47,62.

        Entrar en el primer periodo daría al benchmark una ventaja que la estrategia no tiene:
        el motor decide con el primer periodo cerrado y ejecuta en la apertura siguiente.
        """
        serie = series_from_closes([100.0, 105.0, 110.0])
        resultado = buy_and_hold(serie, capital=D(1000), friction=SIN_FRICCION)

        assert resultado.quantity == D("9.52380952")
        assert D("47.6") < resultado.net_result < D("47.7")

    def test_un_mercado_que_baja_da_perdida(self) -> None:
        serie = series_from_closes([100.0, 90.0, 80.0])
        assert buy_and_hold(serie, capital=D(1000), friction=SIN_FRICCION).net_result < 0

    def test_un_mercado_plano_no_da_nada(self) -> None:
        serie = series_from_closes([100.0] * 10)
        assert buy_and_hold(serie, capital=D(1000), friction=SIN_FRICCION).net_result == D(0)

    def test_la_friccion_tambien_se_aplica_al_benchmark(self) -> None:
        """Comparar sin costes al benchmark seria hacer trampa a favor de la estrategia."""
        serie = series_from_closes([100.0, 110.0])
        limpio = buy_and_hold(serie, capital=D(1000), friction=SIN_FRICCION)
        con_costes = buy_and_hold(serie, capital=D(1000), friction=CON_FRICCION)
        assert con_costes.net_result < limpio.net_result

    def test_solo_paga_dos_comisiones(self) -> None:
        """Una entrada y una salida: mantener no cuesta nada mientras tanto."""
        serie = series_from_closes([100.0] * 200)
        resultado = buy_and_hold(serie, capital=D(10000), friction=CON_FRICCION)
        assert resultado.costs < D(30)

    def test_una_serie_de_un_solo_periodo_no_permite_comprar(self) -> None:
        """Sin periodo siguiente no hay apertura donde entrar: mismo criterio que el motor."""
        resultado = buy_and_hold(
            series_from_closes([100.0]), capital=D(1000), friction=SIN_FRICCION
        )
        assert resultado.net_result == D(0)


class TestDrawdown:
    def test_se_reporta_el_drawdown_del_benchmark(self) -> None:
        """Ganar menos sufriendo mucho menos es un resultado legitimo."""
        serie = series_from_closes(v_shape(60))
        resultado = buy_and_hold(serie, capital=D(10000), friction=SIN_FRICCION)
        assert resultado.max_drawdown < 0

    def test_un_mercado_siempre_alcista_no_tiene_drawdown(self) -> None:
        serie = series_from_closes(ramp(50))
        assert buy_and_hold(serie, capital=D(10000), friction=SIN_FRICCION).max_drawdown == D(0)


class TestEnElInforme:
    def test_el_informe_incluye_el_benchmark(self) -> None:
        from invest_ll.engine.backtest import run_backtest
        from invest_ll.strategy.moving_average import MovingAverageCrossover

        serie = series_from_closes(v_shape(120))
        informe = run_backtest(
            serie,
            MovingAverageCrossover(short=5, long=20),
            initial_capital=D(10000),
            friction=CON_FRICCION,
            risk=RiskConfig(position_fraction=D(1)),
        )
        assert informe.buy_and_hold is not None

    def test_el_exceso_es_la_diferencia(self) -> None:
        from invest_ll.engine.backtest import run_backtest
        from invest_ll.strategy.moving_average import MovingAverageCrossover

        informe = run_backtest(
            series_from_closes(v_shape(120)),
            MovingAverageCrossover(short=5, long=20),
            initial_capital=D(10000),
            friction=CON_FRICCION,
            risk=RiskConfig(position_fraction=D(1)),
        )
        assert informe.buy_and_hold is not None
        esperado = informe.net_result - informe.buy_and_hold.net_result
        assert informe.excess_return == esperado

    def test_la_salida_dice_si_bate_al_mercado(self) -> None:
        from invest_ll.engine.backtest import run_backtest

        from .helpers_strategies import NuncaOpera

        informe = run_backtest(
            series_from_closes(ramp(60)),  # mercado alcista: no operar pierde contra mantener
            NuncaOpera(),
            initial_capital=D(10000),
            friction=CON_FRICCION,
            risk=RiskConfig(position_fraction=D(1)),
        )
        texto = informe.render().lower()
        assert "comprar y mantener" in texto
        assert "no bate" in texto

    def test_una_estrategia_que_gana_mas_se_reconoce(self) -> None:
        """Mercado bajista: no operar bate a mantener."""
        from invest_ll.engine.backtest import run_backtest

        from .helpers_strategies import NuncaOpera

        bajista = [200.0 - i for i in range(60)]
        informe = run_backtest(
            series_from_closes(bajista),
            NuncaOpera(),
            initial_capital=D(10000),
            friction=CON_FRICCION,
            risk=RiskConfig(position_fraction=D(1)),
        )
        assert informe.excess_return > 0
        assert "bate" in informe.render().lower()

    def test_la_salida_sigue_siendo_imprimible_en_windows(self) -> None:
        from invest_ll.engine.backtest import run_backtest
        from invest_ll.strategy.moving_average import MovingAverageCrossover

        informe = run_backtest(
            series_from_closes(v_shape(120)),
            MovingAverageCrossover(short=5, long=20),
            initial_capital=D(10000),
            friction=CON_FRICCION,
            risk=RiskConfig(position_fraction=D(1)),
        )
        informe.render().encode("cp1252")

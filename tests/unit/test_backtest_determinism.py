"""El backtester da el mismo resultado con la misma entrada. Siempre.

Es el Principio I del proyecto (FR-005) convertido en comprobación mecánica, y no es una
formalidad: un motor no determinista invalida todo lo que hay encima. Si dos ejecuciones sobre los
mismos datos dan cifras distintas, comparar dos estrategias deja de significar nada, la reserva de
datos no protege de nada, y un backtest de hace tres meses no se puede reproducir hoy.

El no determinismo casi nunca se escribe a propósito: entra por iterar un `set`, por un `dict` con
orden accidental, por un `float` que se acumula en distinto orden, o por leer el reloj. Por eso
aquí no se prueban tres casos escogidos a mano, sino cientos generados por Hypothesis: es la
diferencia entre "no lo he visto fallar" y "no falla".

Las propiedades que se exigen:

- **Repetible**: dos ejecuciones idénticas dan cifras idénticas.
- **Aislada**: el resultado no depende de qué backtests se corrieron antes.
- **Coherente**: el neto es lo que dicen las operaciones y la curva de patrimonio.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from invest_ll.engine.backtest import run_backtest
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.report.report import BacktestReport
from invest_ll.strategy.breakout import BreakoutHighs
from invest_ll.strategy.moving_average import MovingAverageCrossover
from invest_ll.strategy.price_vs_average import PriceVsAverage
from invest_ll.strategy.protocol import Strategy

from ..fixtures.builders import series_from_closes, v_shape

D = Decimal
CAPITAL = D(10_000)
FRICCION = FrictionConfig(commission_rate=D("0.001"), slippage_rate=D("0.0005"))
RIESGO = RiskConfig(position_fraction=D(1))

# Precios plausibles: positivos, acotados y con suficientes velas para que las medias arranquen.
precios = st.lists(
    st.floats(min_value=1.0, max_value=10_000.0, allow_nan=False, allow_infinity=False),
    min_size=25,
    max_size=90,
)

ESTRATEGIAS: st.SearchStrategy[Strategy] = st.sampled_from(
    [
        MovingAverageCrossover(short=3, long=8),
        BreakoutHighs(lookback=5),
        PriceVsAverage(periods=5),
    ]
)


def correr(cierres: list[float], estrategia: Strategy) -> BacktestReport:
    return run_backtest(
        series_from_closes(cierres),
        estrategia,
        initial_capital=CAPITAL,
        friction=FRICCION,
        risk=RIESGO,
    )


class TestMismaEntradaMismoResultado:
    @given(cierres=precios, estrategia=ESTRATEGIAS)
    @settings(max_examples=60, deadline=None)
    def test_dos_ejecuciones_dan_lo_mismo(self, cierres: list[float], estrategia: Strategy) -> None:
        primera, segunda = correr(cierres, estrategia), correr(cierres, estrategia)

        assert primera.net_result == segunda.net_result
        assert primera.trade_count == segunda.trade_count
        assert primera.total_costs == segunda.total_costs
        assert primera.max_drawdown == segunda.max_drawdown
        assert primera.equity_curve == segunda.equity_curve

    @given(cierres=precios, estrategia=ESTRATEGIAS)
    @settings(max_examples=40, deadline=None)
    def test_las_operaciones_son_las_mismas_una_a_una(
        self, cierres: list[float], estrategia: Strategy
    ) -> None:
        """Cuadrar el total no basta: dos caminos distintos pueden sumar lo mismo."""
        primera, segunda = correr(cierres, estrategia), correr(cierres, estrategia)

        def detalle(informe: BacktestReport) -> list[tuple[object, ...]]:
            return [
                (
                    t.entry_order.signal_timestamp,
                    t.entry_order.execution_timestamp,
                    t.entry_order.fill_price,
                    t.exit_reason,
                    t.gross_pnl,
                    t.costs,
                )
                for t in informe.trades
            ]

        assert detalle(primera) == detalle(segunda)

    @given(cierres=precios, estrategia=ESTRATEGIAS)
    @settings(max_examples=40, deadline=None)
    def test_correr_otro_backtest_en_medio_no_cambia_nada(
        self, cierres: list[float], estrategia: Strategy
    ) -> None:
        """Estado compartido entre ejecuciones: el fallo clasico de un motor con memoria."""
        primera = correr(cierres, estrategia)
        correr([100.0 + i for i in range(40)], estrategia)  # ruido de por medio
        correr(list(reversed(cierres)), estrategia)
        segunda = correr(cierres, estrategia)

        assert primera.net_result == segunda.net_result
        assert primera.equity_curve == segunda.equity_curve


class TestLasCifrasCuadranEntreSi:
    @given(cierres=precios, estrategia=ESTRATEGIAS)
    @settings(max_examples=60, deadline=None)
    def test_el_neto_es_la_suma_de_las_operaciones(
        self, cierres: list[float], estrategia: Strategy
    ) -> None:
        informe = correr(cierres, estrategia)
        if not informe.trades:
            assert informe.net_result == 0
            return

        assert informe.net_result == sum(t.net_pnl for t in informe.trades)

    @given(cierres=precios, estrategia=ESTRATEGIAS)
    @settings(max_examples=60, deadline=None)
    def test_el_drawdown_nunca_es_positivo(
        self, cierres: list[float], estrategia: Strategy
    ) -> None:
        assert correr(cierres, estrategia).max_drawdown <= 0

    @given(cierres=precios, estrategia=ESTRATEGIAS)
    @settings(max_examples=60, deadline=None)
    def test_operar_nunca_sale_gratis(self, cierres: list[float], estrategia: Strategy) -> None:
        """Con comision y slippage declarados, cualquier operacion deja coste. Principio IV."""
        informe = correr(cierres, estrategia)
        if informe.trade_count:
            assert informe.total_costs > 0
        else:
            assert informe.total_costs == 0

    @given(cierres=precios, estrategia=ESTRATEGIAS)
    @settings(max_examples=40, deadline=None)
    def test_la_curva_de_patrimonio_acompana_a_sus_marcas(
        self, cierres: list[float], estrategia: Strategy
    ) -> None:
        informe = correr(cierres, estrategia)
        assert len(informe.equity_curve) == len(informe.equity_timestamps)
        assert list(informe.equity_timestamps) == sorted(informe.equity_timestamps)


class TestElMotorDeVerdadLeeLosDatos:
    """Comprobacion de cordura para los tests de arriba.

    Un motor que devolviera siempre lo mismo pasaria todas las pruebas de repetibilidad sin
    ejecutar nada. Estos dos casos concretos fijan que el resultado SI depende de la entrada; sin
    ellos, "determinista" podria significar "inerte".
    """

    def test_una_serie_distinta_da_un_resultado_distinto(self) -> None:
        """Se usa una V y no una rampa: sin cruce de medias no hay operacion que comparar."""
        estrategia = MovingAverageCrossover(short=3, long=8)
        en_v = correr(v_shape(40), estrategia)
        oscilante = correr([100.0 + (8 if i % 6 < 3 else -8) for i in range(60)], estrategia)

        assert en_v.net_result != oscilante.net_result
        assert en_v.trade_count != oscilante.trade_count

    def test_mas_comision_deja_menos_dinero(self) -> None:
        """Si la friccion no se aplicara, este test no notaria la diferencia."""
        cierres = [100.0 + (8 if i % 6 < 3 else -8) for i in range(60)]
        estrategia = MovingAverageCrossover(short=3, long=8)
        serie = series_from_closes(cierres)

        barato = run_backtest(
            serie,
            estrategia,
            initial_capital=CAPITAL,
            friction=FrictionConfig(commission_rate=D("0.0001"), slippage_rate=D(0)),
            risk=RIESGO,
        )
        caro = run_backtest(
            serie,
            estrategia,
            initial_capital=CAPITAL,
            friction=FrictionConfig(commission_rate=D("0.02"), slippage_rate=D("0.01")),
            risk=RIESGO,
        )

        if barato.trade_count:
            assert caro.total_costs > barato.total_costs
            assert caro.net_result < barato.net_result

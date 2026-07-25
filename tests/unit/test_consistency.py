"""Métricas de consistencia mensual.

Responden al objetivo declarado del operador: "mantener un indice positivo aunque no sea mucho".
Sin estas cifras el informe no permite juzgar si eso se cumple.

Y llevan su propia salvaguarda: el porcentaje de meses en verde se reporta SIEMPRE junto al peor
mes, porque una racha larga de meses positivos seguida de un desplome es el perfil clasico de las
estrategias que arruinan a quien las usa.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from invest_ll.report.consistency import monthly_consistency

D = Decimal
DIA = timedelta(days=1)
INICIO = datetime(2025, 1, 1, tzinfo=UTC)


def _serie_larga() -> list[float]:
    """Onda de 400 velas que nunca baja de cero: v_shape con base 100 llegaria a negativos."""
    import math

    return [1000.0 + 200.0 * math.sin(i / 40.0) for i in range(400)]


def curva(valores: list[float], *, dias_por_paso: int = 1):  # type: ignore[no-untyped-def]
    equity = [D(str(v)) for v in valores]
    marcas = [INICIO + DIA * (i * dias_por_paso) for i in range(len(valores))]
    return equity, marcas


def test_una_curva_vacia_no_rompe() -> None:
    resultado = monthly_consistency([], [])
    assert resultado.periods == 0
    assert resultado.positive_ratio == 0.0


def test_cuenta_los_meses_positivos() -> None:
    # Un valor cada 15 dias durante seis meses, siempre subiendo.
    equity, marcas = curva([100, 110, 120, 130, 140, 150, 160, 170], dias_por_paso=15)
    resultado = monthly_consistency(equity, marcas)
    assert resultado.periods >= 3
    assert resultado.positive_ratio == 1.0


def test_detecta_meses_negativos() -> None:
    equity, marcas = curva([100, 90, 80, 70, 60, 50], dias_por_paso=31)
    resultado = monthly_consistency(equity, marcas)
    assert resultado.positive_periods == 0
    assert resultado.worst_period < 0


def test_la_racha_perdedora_mas_larga() -> None:
    equity, marcas = curva([100, 90, 80, 70, 120, 110], dias_por_paso=31)
    resultado = monthly_consistency(equity, marcas)
    assert resultado.longest_losing_streak == 3


def test_el_mejor_y_el_peor_mes() -> None:
    equity, marcas = curva([100, 150, 140, 200], dias_por_paso=31)
    resultado = monthly_consistency(equity, marcas)
    assert resultado.best_period > 0
    assert resultado.worst_period < 0


class TestAsimetria:
    """La cifra que desmonta un porcentaje de aciertos bonito."""

    def test_el_perfil_peligroso_se_detecta(self) -> None:
        """Once meses ganando poco y uno perdiendo mucho: 92% de meses en verde y ruina.

        Es exactamente el patron de vender opciones o promediar a la baja.
        """
        valores = [100.0]
        for _ in range(11):
            valores.append(valores[-1] + 2)
        valores.append(valores[-1] - 50)  # el mes que se lo lleva todo

        equity, marcas = curva(valores, dias_por_paso=31)
        resultado = monthly_consistency(equity, marcas)

        assert resultado.positive_ratio > 0.9, "el porcentaje de meses en verde es altisimo"
        assert resultado.asymmetry > 20, "y aun asi el peor mes se come veinte meses buenos"

    def test_un_perfil_equilibrado_tiene_asimetria_baja(self) -> None:
        equity, marcas = curva([100, 110, 100, 110, 100, 110], dias_por_paso=31)
        resultado = monthly_consistency(equity, marcas)
        assert resultado.asymmetry <= 2

    def test_sin_meses_buenos_la_asimetria_es_cero(self) -> None:
        """Evita dividir por cero cuando no hubo ningun mes positivo."""
        equity, marcas = curva([100, 90, 80], dias_por_paso=31)
        assert monthly_consistency(equity, marcas).asymmetry == 0


class TestEnElInforme:
    def test_el_informe_incluye_la_consistencia(self) -> None:
        from invest_ll.engine.backtest import run_backtest
        from invest_ll.engine.config import FrictionConfig, RiskConfig
        from invest_ll.strategy.moving_average import MovingAverageCrossover

        from ..fixtures.builders import series_from_closes

        informe = run_backtest(
            series_from_closes(_serie_larga()),
            MovingAverageCrossover(short=5, long=20),
            initial_capital=D(10000),
            friction=FrictionConfig(commission_rate=D("0.001"), slippage_rate=D(0)),
            risk=RiskConfig(position_fraction=D(1)),
        )
        assert informe.consistency is not None
        assert informe.consistency.periods > 0

    def test_la_salida_muestra_meses_en_verde_y_peor_mes_juntos(self) -> None:
        """Nunca uno sin el otro: el porcentaje solo, engaña."""
        from invest_ll.engine.backtest import run_backtest
        from invest_ll.engine.config import FrictionConfig, RiskConfig
        from invest_ll.strategy.moving_average import MovingAverageCrossover

        from ..fixtures.builders import series_from_closes

        informe = run_backtest(
            series_from_closes(_serie_larga()),
            MovingAverageCrossover(short=5, long=20),
            initial_capital=D(10000),
            friction=FrictionConfig(commission_rate=D("0.001"), slippage_rate=D(0)),
            risk=RiskConfig(position_fraction=D(1)),
        )
        texto = informe.render().lower()
        assert "meses en verde" in texto
        assert "peor mes" in texto
        texto.encode("cp1252")

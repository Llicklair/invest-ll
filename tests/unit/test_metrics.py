"""T022 — cálculo de métricas (FR-011).

Estas cifras son el veredicto. Si mienten, todo lo demás da igual.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from invest_ll.report.metrics import expectancy, max_drawdown, win_rate

D = Decimal


class TestExpectancy:
    def test_media_de_resultados(self) -> None:
        assert expectancy([D(10), D(-5), D(15), D(-20)]) == D(0)

    def test_expectancy_positiva(self) -> None:
        assert expectancy([D(10), D(20)]) == D(15)

    def test_sin_operaciones_es_cero(self) -> None:
        assert expectancy([]) == D(0)

    def test_win_rate_alto_con_expectancy_negativa(self) -> None:
        """El caso que justifica todo el Principio III.

        Nueve aciertos de 1 y un fallo de 20: acierta el 90% y pierde dinero.
        """
        resultados = [D(1)] * 9 + [D(-20)]
        assert win_rate(resultados) == pytest.approx(0.9)
        assert expectancy(resultados) < 0


class TestMaxDrawdown:
    def test_caida_desde_maximo(self) -> None:
        """Sube a 120, cae a 90: la peor caída desde un máximo es 30."""
        equity = [D(100), D(120), D(90), D(110)]
        assert max_drawdown(equity) == D(-30)

    def test_curva_siempre_creciente_no_tiene_drawdown(self) -> None:
        assert max_drawdown([D(100), D(110), D(120)]) == D(0)

    def test_nunca_es_positivo(self) -> None:
        assert max_drawdown([D(100), D(200), D(50), D(300)]) <= 0

    def test_curva_vacia_es_cero(self) -> None:
        assert max_drawdown([]) == D(0)

    def test_toma_la_peor_caida_no_la_ultima(self) -> None:
        equity = [D(100), D(50), D(100), D(95)]
        assert max_drawdown(equity) == D(-50)


class TestWinRate:
    def test_proporcion_de_ganadoras(self) -> None:
        assert win_rate([D(10), D(-5), D(10), D(-5)]) == pytest.approx(0.5)

    def test_todas_ganadoras(self) -> None:
        assert win_rate([D(1), D(2)]) == pytest.approx(1.0)

    def test_sin_operaciones_es_cero(self) -> None:
        assert win_rate([]) == 0.0

    def test_operacion_plana_no_cuenta_como_ganadora(self) -> None:
        assert win_rate([D(0), D(10)]) == pytest.approx(0.5)

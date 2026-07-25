"""Estimación de coste antes de lanzar (T019, FR-041).

Existe porque el operador eligió que el LLM decida también el cuándo: a una decisión por vela, un
backtest largo cuesta cientos de euros. Eso no puede salir de un comando lanzado por descuido.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from invest_ll.decision.cost import UMBRAL_CONFIRMACION, estimate_cost


class TestCuentaLoQueSePaga:
    def test_solo_se_pagan_las_nuevas(self) -> None:
        e = estimate_cost(252, cached_decisions=200)
        assert e.new_decisions == 52

    def test_todo_cacheado_cuesta_cero(self) -> None:
        e = estimate_cost(252, cached_decisions=252)
        assert e.new_decisions == 0
        assert e.estimated_cost == 0
        assert "identico al anterior" in e.render()

    def test_mas_cacheadas_que_totales_no_da_negativo(self) -> None:
        assert estimate_cost(10, cached_decisions=99).new_decisions == 0

    def test_un_backtest_mensual_de_21_anos_es_asumible(self) -> None:
        """252 decisiones: el caso normal. Si esto costara cientos, la feature seria inusable."""
        assert estimate_cost(252).estimated_cost < Decimal(20)

    def test_un_backtest_diario_es_caro_y_se_nota(self) -> None:
        e = estimate_cost(5283)
        assert e.estimated_cost > Decimal(100)
        assert e.needs_confirmation


class TestConfirmacion:
    def test_por_debajo_del_umbral_no_pregunta(self) -> None:
        assert not estimate_cost(UMBRAL_CONFIRMACION - 1).needs_confirmation

    def test_por_encima_del_umbral_pregunta(self) -> None:
        assert estimate_cost(UMBRAL_CONFIRMACION + 1).needs_confirmation

    def test_el_cache_puede_evitar_la_confirmacion(self) -> None:
        """Repetir un experimento caro no deberia volver a pedir permiso: ya esta pagado."""
        e = estimate_cost(5000, cached_decisions=4990)
        assert not e.needs_confirmation

    def test_el_umbral_es_configurable(self) -> None:
        assert estimate_cost(50, threshold=10).needs_confirmation


class TestSalida:
    def test_el_aviso_dice_cuantas_y_cuanto(self) -> None:
        texto = estimate_cost(5283).render()
        assert "5283" in texto or "5.283" in texto
        assert "$" in texto

    def test_avisa_de_las_ya_pagadas(self) -> None:
        assert "cacheadas" in estimate_cost(300, cached_decisions=100).render()

    def test_es_imprimible_en_consola_windows(self) -> None:
        estimate_cost(5283).render().encode("cp1252")


class TestValidacion:
    @pytest.mark.parametrize(("total", "cache"), [(-1, 0), (10, -5)])
    def test_los_negativos_se_rechazan(self, total: int, cache: int) -> None:
        with pytest.raises(ValueError, match="negativ"):
            estimate_cost(total, cached_decisions=cache)

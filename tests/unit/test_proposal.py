"""Propuesta de cartera (T033, T035, T037, T038).

El test que define la historia es `test_solo_pide_importe_y_frecuencia`: si para obtener una
propuesta hubiera que elegir estrategia o parámetros, el sistema no serviría a quien ha declarado
no saber de inversión — que es el caso.
"""

from __future__ import annotations

import inspect
from decimal import Decimal

import pytest

from invest_ll.data.universe import build_universe
from invest_ll.engine.config import FrictionConfig
from invest_ll.proposal.builder import (
    EXPLICACION_GENERICA,
    FRECUENCIAS,
    propose_portfolio,
)

from ..fixtures.builders import ORIGIN, ramp, series_from_closes

D = Decimal
FR = FrictionConfig(commission_rate=D("0.001"), slippage_rate=D("0.0005"))


def universo(simbolos: tuple[str, ...] = ("GLD", "TLT"), n: int = 400):  # type: ignore[no-untyped-def]
    return build_universe(
        [
            series_from_closes(ramp(n, start=50.0 + i * 10), symbol=s, start=ORIGIN)
            for i, s in enumerate(simbolos)
        ]
    )


class TestLoQueSePide:
    def test_solo_pide_importe_y_frecuencia(self) -> None:
        """FR-005: elegir estrategia y parametros es justo lo que el operador no sabe hacer."""
        firma = inspect.signature(propose_portfolio)
        obligatorios = {
            n
            for n, p in firma.parameters.items()
            if p.default is inspect.Parameter.empty and n != "universe"
        }
        assert obligatorios <= {"amount", "friction"}

    def test_devuelve_una_cartera_concreta_con_cantidades(self) -> None:
        p = propose_portfolio(universo(), amount=D(500), friction=FR)
        assert len(p.holdings) == 2
        for h in p.holdings:
            assert h.amount_per_contribution > 0

    def test_el_reparto_es_a_partes_iguales(self) -> None:
        """Optimizar el reparto sobre datos pasados es mirar la respuesta antes de responder."""
        p = propose_portfolio(universo(("A", "B", "C", "D")), amount=D(400), friction=FR)
        cantidades = {h.amount_per_contribution for h in p.holdings}
        assert len(cantidades) == 1

    def test_no_se_reparte_mas_de_lo_aportado(self) -> None:
        """Con 3 activos y 100 euros, el redondeo no puede hacer que sumen 100.02."""
        p = propose_portfolio(universo(("A", "B", "C")), amount=D(100), friction=FR)
        assert p.total_per_contribution <= D(100)

    @pytest.mark.parametrize("frecuencia", sorted(FRECUENCIAS))
    def test_todas_las_frecuencias_funcionan(self, frecuencia: str) -> None:
        p = propose_portfolio(universo(), amount=D(500), frequency=frecuencia, friction=FR)
        assert p.every_periods == FRECUENCIAS[frecuencia]


class TestTraeSuSimulacion:
    """FR-002, FR-003: una propuesta sin simulacion es una recomendacion a ciegas."""

    def test_toda_propuesta_trae_simulacion(self) -> None:
        p = propose_portfolio(universo(), amount=D(500), friction=FR)
        assert p.simulation is not None
        assert p.simulation.total_contributed > 0

    def test_la_simulacion_incluye_los_costes(self) -> None:
        p = propose_portfolio(universo(), amount=D(500), friction=FR)
        assert p.simulation.total_costs > 0

    def test_trae_la_comparacion_contra_no_hacer_nada(self) -> None:
        p = propose_portfolio(universo(), amount=D(500), friction=FR)
        assert p.simulation.lump_sum_value is not None

    def test_trae_el_analisis_de_diversificacion(self) -> None:
        p = propose_portfolio(universo(), amount=D(500), friction=FR)
        assert p.diversification.effective_assets > 0


class TestExplicaciones:
    """FR-004: en lenguaje que no exige saber de inversion."""

    def test_cada_activo_trae_su_explicacion(self) -> None:
        p = propose_portfolio(universo(("GLD", "TLT")), amount=D(500), friction=FR)
        for h in p.holdings:
            assert h.explanation
            assert h.explanation != EXPLICACION_GENERICA

    def test_un_activo_desconocido_no_se_inventa_una_explicacion(self) -> None:
        p = propose_portfolio(universo(("ZZZZ", "GLD")), amount=D(500), friction=FR)
        desconocido = next(h for h in p.holdings if h.symbol == "ZZZZ")
        assert desconocido.explanation == EXPLICACION_GENERICA

    def test_las_explicaciones_no_prometen_nada(self) -> None:
        from invest_ll.proposal.builder import EXPLICACIONES

        for texto in EXPLICACIONES.values():
            bajo = texto.lower()
            assert "garantiza" not in bajo
            assert "seguro" not in bajo
            assert "sin riesgo" not in bajo


class TestSalida:
    def test_la_diversificacion_se_lee_antes_que_la_ganancia(self) -> None:
        """Si diversifica mal, eso importa mas que cuanto habria ganado."""
        texto = propose_portfolio(universo(), amount=D(500), friction=FR).render()
        assert texto.index("Diversificacion") < texto.index("Ganancia")

    def test_es_imprimible_en_consola_windows(self) -> None:
        propose_portfolio(universo(), amount=D(500), friction=FR).render().encode("cp1252")


class TestValidacion:
    @pytest.mark.parametrize("importe", [D(0), D(-100)])
    def test_un_importe_no_positivo_se_rechaza(self, importe: Decimal) -> None:
        with pytest.raises(ValueError, match="positiva"):
            propose_portfolio(universo(), amount=importe, friction=FR)

    def test_una_frecuencia_desconocida_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="frecuencia desconocida"):
            propose_portfolio(universo(), amount=D(500), frequency="cada rato", friction=FR)

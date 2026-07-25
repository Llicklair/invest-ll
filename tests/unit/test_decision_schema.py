"""Lectura de la respuesta del modelo (T008, T011).

El test que más importa aquí es el que comprueba que NUNCA se inventa una decisión. Un sistema que
ante una respuesta rara devuelve "mantener" produce informes que describen algo que no pasó.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from invest_ll.data.universe import build_universe
from invest_ll.decision.models import Action
from invest_ll.decision.prompt import render_context, symbol_map
from invest_ll.decision.schema import DecisionParseError, parse_decision
from invest_ll.engine.universe_view import UniverseView

from ..fixtures.builders import ORIGIN, ramp, series_from_closes

CUANDO = datetime(2020, 6, 1, tzinfo=UTC)


def respuesta(**cambios: object) -> str:
    base: dict[str, object] = {
        "summary": "el activo A lidera",
        "assets": [
            {"symbol": "A", "action": "enter", "weight": 0.6, "reasoning": "sube mas"},
        ],
    }
    base.update(cambios)
    return json.dumps(base)


class TestLecturaValida:
    def test_una_respuesta_correcta_se_convierte(self) -> None:
        d = parse_decision(respuesta(), timestamp=CUANDO, model="m")
        assert d.assets[0].symbol == "A"
        assert d.assets[0].action is Action.ENTER
        assert d.chosen == "A"

    def test_traduce_las_etiquetas_a_simbolos_reales(self) -> None:
        d = parse_decision(
            respuesta(), timestamp=CUANDO, model="m", symbol_map={"A": "AAPL", "B": "GLD"}
        )
        assert d.assets[0].symbol == "AAPL"

    def test_quedarse_fuera_es_valido(self) -> None:
        d = parse_decision(
            json.dumps({"summary": "todo cae", "assets": []}), timestamp=CUANDO, model="m"
        )
        assert d.chosen is None

    def test_el_peso_no_arrastra_error_de_coma_flotante(self) -> None:
        """Estos pesos multiplican cifras de dinero: Decimal(str(x)), no Decimal(float)."""
        d = parse_decision(
            json.dumps(
                {
                    "summary": "x",
                    "assets": [{"symbol": "A", "action": "enter", "weight": 0.1, "reasoning": "r"}],
                }
            ),
            timestamp=CUANDO,
            model="m",
        )
        assert str(d.assets[0].weight) == "0.1"


class TestNuncaInventa:
    """FR-011: lo que no se entiende es un fallo, nunca una decision por defecto."""

    @pytest.mark.parametrize(
        "payload",
        [
            "no soy json",
            "[1, 2, 3]",
            '{"assets": []}',
            '{"summary": "x"}',
            '{"summary": "x", "assets": "no es lista"}',
        ],
    )
    def test_una_respuesta_ininteligible_lanza(self, payload: str) -> None:
        with pytest.raises(DecisionParseError):
            parse_decision(payload, timestamp=CUANDO, model="m")

    def test_un_peso_fuera_de_rango_lanza(self) -> None:
        payload = json.dumps(
            {
                "summary": "x",
                "assets": [{"symbol": "A", "action": "enter", "weight": 1.5, "reasoning": "r"}],
            }
        )
        with pytest.raises(DecisionParseError, match="entre 0 y 1"):
            parse_decision(payload, timestamp=CUANDO, model="m")

    def test_la_suma_de_pesos_por_encima_de_uno_lanza(self) -> None:
        payload = json.dumps(
            {
                "summary": "x",
                "assets": [
                    {"symbol": "A", "action": "enter", "weight": 0.7, "reasoning": "r"},
                    {"symbol": "B", "action": "enter", "weight": 0.6, "reasoning": "r"},
                ],
            }
        )
        with pytest.raises(DecisionParseError, match="suma de pesos"):
            parse_decision(payload, timestamp=CUANDO, model="m")

    def test_un_activo_que_no_existe_lanza(self) -> None:
        """Si el modelo elige algo fuera del universo, es un fallo, no una decision."""
        payload = json.dumps(
            {
                "summary": "x",
                "assets": [{"symbol": "Z", "action": "enter", "weight": 0.5, "reasoning": "r"}],
            }
        )
        with pytest.raises(DecisionParseError, match="no esta en el universo"):
            parse_decision(payload, timestamp=CUANDO, model="m", symbol_map={"A": "AAPL"})

    def test_una_accion_desconocida_lanza(self) -> None:
        payload = json.dumps(
            {
                "summary": "x",
                "assets": [
                    {"symbol": "A", "action": "comprar_mucho", "weight": 0.5, "reasoning": "r"}
                ],
            }
        )
        with pytest.raises(DecisionParseError, match="accion desconocida"):
            parse_decision(payload, timestamp=CUANDO, model="m")

    def test_sin_razonamiento_lanza(self) -> None:
        payload = json.dumps(
            {
                "summary": "x",
                "assets": [{"symbol": "A", "action": "enter", "weight": 0.5, "reasoning": ""}],
            }
        )
        with pytest.raises(DecisionParseError, match="razonamiento"):
            parse_decision(payload, timestamp=CUANDO, model="m")


def vista(n: int = 200, cursor: int = 150) -> UniverseView:
    universo = build_universe(
        [
            series_from_closes(ramp(n), symbol="AAPL"),
            series_from_closes(ramp(n, start=50.0), symbol="GLD", start=ORIGIN),
        ]
    )
    return UniverseView(universe=universo, cursor=cursor)


class TestContexto:
    def test_el_texto_no_menciona_fechas(self) -> None:
        """FR-010: sin fechas, el modelo tiene menos asideros para reconocer el periodo."""
        texto = render_context(vista())
        for fragmento in ("2020", "2021", "-01-", "enero", "January"):
            assert fragmento not in texto

    def test_el_texto_no_menciona_los_simbolos_reales(self) -> None:
        texto = render_context(vista())
        assert "AAPL" not in texto
        assert "GLD" not in texto
        assert "Activo A" in texto

    def test_con_anonimato_desactivado_si_aparecen(self) -> None:
        texto = render_context(vista(), anonymous=False)
        assert "AAPL" in texto

    def test_los_precios_van_normalizados(self) -> None:
        """Un precio absoluto es una pista sobre que activo es."""
        texto = render_context(vista())
        assert "100.0" in texto

    def test_el_mapa_traduce_de_vuelta(self) -> None:
        assert symbol_map(vista()) == {"A": "AAPL", "B": "GLD"}

    def test_el_contexto_no_incluye_datos_posteriores_al_cursor(self) -> None:
        """La garantia estructural: el texto de un cursor temprano no puede contener
        informacion que solo existe mas adelante."""
        pronto = render_context(vista(cursor=50))
        tarde = render_context(vista(cursor=190))
        assert pronto != tarde

    def test_es_imprimible_en_consola_windows(self) -> None:
        render_context(vista()).encode("cp1252")

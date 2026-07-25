"""El proveedor que usa el CLI de Claude Code.

Con un doble en lugar del ejecutable real: la suite no puede depender de que haya una sesión
iniciada ni gastar cuota.

Lo que más se prueba aquí es la **tolerancia al formato**. Sin esquema forzado el modelo a veces
envuelve el JSON en un bloque de código o le pone una frase delante — eso es la misma decisión con
adorno, y aceptarla no es indulgencia. Lo que sigue siendo un fallo es una respuesta de la que no
se puede extraer una decisión.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from invest_ll.decision.cli_provider import (
    ClaudeCliProvider,
    extraer_resultado,
    limpiar_respuesta,
)
from invest_ll.decision.models import DecisionRequest
from invest_ll.decision.schema import DecisionParseError, DecisionUnavailableError

CUANDO = datetime(2020, 6, 1, tzinfo=UTC)

DECISION_JSON = json.dumps(
    {
        "summary": "el activo A lidera",
        "assets": [{"symbol": "A", "action": "enter", "weight": 0.7, "reasoning": "sube mas"}],
    }
)


def peticion() -> DecisionRequest:
    return DecisionRequest(
        timestamp=CUANDO,
        symbols=("AAPL", "GLD"),
        market_context="Activo A: +5%\nActivo B: -2%",
        instructions_version="v1",
        model="claude-opus-4-6",
    )


def proveedor(respuesta: str) -> ClaudeCliProvider:
    def responder(_: str) -> str:
        return respuesta

    return ClaudeCliProvider(runner=responder)


class TestRespuestasLimpias:
    def test_un_json_pelado_se_lee(self) -> None:
        d = proveedor(DECISION_JSON).decide(peticion())
        assert d.chosen == "A"

    def test_conserva_el_instante_pedido(self) -> None:
        """Devolver otra fecha seria mezclar instantes, que es look-ahead con otro nombre."""
        assert proveedor(DECISION_JSON).decide(peticion()).timestamp == CUANDO

    def test_registra_el_modelo(self) -> None:
        assert proveedor(DECISION_JSON).decide(peticion()).model == "claude-opus-4-6"


class TestToleranciaAlFormato:
    """Sin esquema forzado, el modelo adorna. Eso no invalida la decision."""

    def test_acepta_un_bloque_de_codigo(self) -> None:
        envuelto = f"```json\n{DECISION_JSON}\n```"
        assert proveedor(envuelto).decide(peticion()).chosen == "A"

    def test_acepta_un_bloque_sin_lenguaje(self) -> None:
        assert proveedor(f"```\n{DECISION_JSON}\n```").decide(peticion()).chosen == "A"

    def test_acepta_texto_por_delante(self) -> None:
        con_preambulo = f"Aqui esta mi decision:\n\n{DECISION_JSON}"
        assert proveedor(con_preambulo).decide(peticion()).chosen == "A"

    def test_acepta_texto_por_detras(self) -> None:
        con_coletilla = f"{DECISION_JSON}\n\nEspero que sirva."
        assert proveedor(con_coletilla).decide(peticion()).chosen == "A"

    def test_acepta_espacios_alrededor(self) -> None:
        assert proveedor(f"   \n{DECISION_JSON}\n  ").decide(peticion()).chosen == "A"


class TestLoQueSigueSiendoFallo:
    """FR-011: nunca se inventa una decision."""

    def test_una_respuesta_sin_json_falla(self) -> None:
        with pytest.raises(DecisionParseError, match="no hay ningun objeto JSON"):
            proveedor("Lo siento, no puedo ayudarte con eso.").decide(peticion())

    def test_un_json_que_no_cumple_el_esquema_falla(self) -> None:
        with pytest.raises(DecisionParseError):
            proveedor('{"otra": "cosa"}').decide(peticion())

    def test_un_peso_invalido_falla(self) -> None:
        malo = json.dumps(
            {
                "summary": "x",
                "assets": [{"symbol": "A", "action": "enter", "weight": 3.0, "reasoning": "r"}],
            }
        )
        with pytest.raises(DecisionParseError, match="entre 0 y 1"):
            proveedor(malo).decide(peticion())


class TestEnvoltorioDelCli:
    def test_extrae_el_texto_del_sobre(self) -> None:
        sobre = json.dumps({"type": "result", "is_error": False, "result": "hola"})
        assert extraer_resultado(sobre) == "hola"

    def test_un_error_del_cli_se_propaga(self) -> None:
        sobre = json.dumps({"is_error": True, "result": "Not logged in"})
        with pytest.raises(DecisionUnavailableError, match="Not logged in"):
            extraer_resultado(sobre)

    def test_una_salida_que_no_es_json_falla(self) -> None:
        with pytest.raises(DecisionUnavailableError, match="no devolvio JSON"):
            extraer_resultado("command not found")

    def test_un_sobre_sin_texto_falla(self) -> None:
        with pytest.raises(DecisionUnavailableError, match="no trae texto"):
            extraer_resultado(json.dumps({"is_error": False}))


class TestLimpieza:
    @pytest.mark.parametrize(
        "entrada",
        [
            '{"a":1}',
            '```json\n{"a":1}\n```',
            '```\n{"a":1}\n```',
            'texto\n{"a":1}\ntexto',
            '   {"a":1}   ',
        ],
    )
    def test_extrae_el_objeto_en_todos_los_envoltorios(self, entrada: str) -> None:
        assert limpiar_respuesta(entrada) == '{"a":1}'

    def test_sin_objeto_lanza(self) -> None:
        with pytest.raises(DecisionParseError):
            limpiar_respuesta("aqui no hay nada")


class TestNoSaleALaRedEnLosTests:
    def test_el_proveedor_con_runner_no_invoca_el_ejecutable(self) -> None:
        """Si intentara lanzar el CLI de verdad, este test tardaria segundos o fallaria."""
        llamadas: list[str] = []

        def espia(prompt: str) -> str:
            llamadas.append(prompt)
            return DECISION_JSON

        ClaudeCliProvider(runner=espia).decide(peticion())
        assert len(llamadas) == 1
        assert "Estado del mercado" in llamadas[0]

    def test_el_prompt_incluye_el_esquema_pedido(self) -> None:
        """Sin esquema forzado, pedirlo en el prompt es lo unico que queda."""
        capturado: list[str] = []

        def capturar(prompt: str) -> str:
            capturado.append(prompt)
            return DECISION_JSON

        ClaudeCliProvider(runner=capturar).decide(peticion())
        assert "UNICAMENTE" in capturado[0]
        assert "weight" in capturado[0]

"""Decisiones a través del CLI de Claude Code, usando la suscripción en vez de la API.

**Diferencias frente a `AnthropicProvider` que conviene tener presentes:**

- **No hay salida estructurada garantizada.** La API permite forzar un esquema JSON; el CLI no.
  Aquí se pide el formato en el prompt y se valida al recibirlo. Las respuestas que no encajen se
  tratan como fallo —nunca se inventa una decisión—, pero habrá más fallos que con la API.
- **Es secuencial y lento.** Unos 6 s por decisión, sin descuento por lotes.
- **Arrastra el prompt de sistema de Claude Code**: ~20.000 tokens de contexto por llamada que no
  tienen nada que ver con la decisión. Con suscripción no se factura, pero consume cuota.

Se ejecuta desde un directorio limpio a propósito: si corriera dentro del proyecto cargaría su
`CLAUDE.md` y sus reglas, que no pintan nada en una decisión de inversión y contaminarían el
contexto.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from invest_ll.decision.models import Decision, DecisionRequest
from invest_ll.decision.prompt import INSTRUCCIONES
from invest_ll.decision.schema import (
    ESQUEMA_DECISION,
    DecisionParseError,
    DecisionUnavailableError,
    parse_decision,
)

EJECUTABLE = "claude"
TIMEOUT_SEGUNDOS = 240

FORMATO_PEDIDO = """
Responde UNICAMENTE con un objeto JSON que cumpla este esquema. Sin texto antes ni despues,
sin bloque de codigo, sin explicaciones fuera del JSON:

{esquema}
"""


class ClaudeCliProvider:
    """Pide decisiones al CLI de Claude Code."""

    __slots__ = ("_cwd", "_extra_args", "_model", "_runner")

    def __init__(
        self,
        *,
        model: str = "claude-opus-4-6",
        cwd: Path | None = None,
        runner: Callable[[str], str] | None = None,
    ) -> None:
        self._model = model
        # Directorio neutro: sin CLAUDE.md ni configuracion de proyecto que contamine.
        self._cwd = cwd or Path(tempfile.gettempdir()) / "invest-ll-cli"
        self._runner = runner
        self._extra_args: tuple[str, ...] = (
            "-p",
            "--output-format",
            "json",
            "--disable-slash-commands",
            "--model",
            model,
        )

    @property
    def model(self) -> str:
        return self._model

    def decide(self, request: DecisionRequest) -> Decision:
        salida = self._invocar(self._prompt(request))
        return parse_decision(
            limpiar_respuesta(salida),
            timestamp=request.timestamp,
            model=self._model,
            symbol_map=request.labels or None,
        )

    def decide_many(self, requests: Sequence[DecisionRequest]) -> list[Decision]:
        """Una a una. El CLI no admite lotes."""
        return [self.decide(r) for r in requests]

    def _prompt(self, request: DecisionRequest) -> str:
        return "\n\n".join(
            (
                INSTRUCCIONES,
                FORMATO_PEDIDO.format(esquema=json.dumps(ESQUEMA_DECISION, indent=2)),
                "Estado del mercado:",
                request.market_context,
            )
        )

    def _invocar(self, prompt: str) -> str:
        if self._runner is not None:  # inyectado en los tests
            return self._runner(prompt)

        self._cwd.mkdir(parents=True, exist_ok=True)

        try:
            proceso = subprocess.run(
                [EJECUTABLE, *self._extra_args],
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=TIMEOUT_SEGUNDOS,
                cwd=self._cwd,
                check=False,
            )
        except FileNotFoundError as error:
            raise DecisionUnavailableError(
                f"no se encontro el ejecutable {EJECUTABLE!r} en el PATH"
            ) from error
        except subprocess.TimeoutExpired as error:
            raise DecisionUnavailableError(f"el CLI no respondio en {TIMEOUT_SEGUNDOS}s") from error

        if proceso.returncode != 0:
            raise DecisionUnavailableError(
                f"el CLI fallo (codigo {proceso.returncode}): {proceso.stderr[:200]}"
            )

        return extraer_resultado(proceso.stdout)


def extraer_resultado(stdout: str) -> str:
    """Saca el texto de la respuesta del envoltorio JSON del CLI."""
    try:
        sobre: dict[str, Any] = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise DecisionUnavailableError(f"el CLI no devolvio JSON: {stdout[:200]!r}") from error

    if sobre.get("is_error"):
        raise DecisionUnavailableError(f"el CLI reporto un error: {sobre.get('result')}")

    resultado = sobre.get("result")
    if not isinstance(resultado, str):
        raise DecisionUnavailableError("la respuesta del CLI no trae texto")
    return resultado


def limpiar_respuesta(texto: str) -> str:
    """Quita el bloque de código si el modelo lo añadió pese a pedirle que no.

    No es indulgencia: es reconocer que sin esquema forzado el modelo a veces envuelve el JSON, y
    eso no es una decisión inválida, es la misma decisión con adorno. Lo que sí sigue fallando es
    una respuesta que no contenga un JSON interpretable.
    """
    limpio = texto.strip()
    if limpio.startswith("```"):
        lineas = limpio.splitlines()
        lineas = lineas[1:] if len(lineas) > 1 else lineas
        if lineas and lineas[-1].strip().startswith("```"):
            lineas = lineas[:-1]
        limpio = "\n".join(lineas).strip()

    # A veces llega texto antes o despues del objeto. Se recorta al primer objeto completo.
    inicio = limpio.find("{")
    fin = limpio.rfind("}")
    if inicio == -1 or fin == -1 or fin < inicio:
        raise DecisionParseError(f"no hay ningun objeto JSON en la respuesta: {texto[:150]!r}")
    return limpio[inicio : fin + 1]

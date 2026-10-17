"""Hablar con Claude sobre TU situación, con las reglas de la casa dentro del prompt.

Usa el CLI de `claude` con tu suscripción, igual que `invest-ll-generate` — no la API de pago.
Cada mensaje gasta cuota.

**El chat no puede ejecutar nada, y no es una limitación técnica sino el diseño**: sus
instrucciones le obligan a proponer el comando exacto y recordar que la confirmación es humana.
Un chat que pudiera lanzar órdenes sería un agente operando con tu dinero — justo lo que el
Principio I prohíbe. `test_chat.py::test_las_instrucciones_prohiben_ejecutar` lo fija.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from invest_ll.claude_cli import ejecutable
from invest_ll.errors import InvestLLError

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

EJECUTABLE = "claude"
TIMEOUT_SEGUNDOS = 180
MODELO_POR_DEFECTO = "claude-opus-4-6"
MAX_TURNOS_EN_PROMPT = 10

INSTRUCCIONES = """\
Eres el asistente de INVEST LL, una aplicacion de inversion cuyo principio central es que el
sistema no puede mentirle al operador sobre sus propios resultados. El operador no es experto en
inversion. Respondes en espanol, directo y sin adornos.

Reglas NO negociables, en este orden:

1. NO PUEDES EJECUTAR NADA. No tienes acceso a ordenes, ficheros ni comandos. Cuando la accion
   corresponda, propone el comando exacto (invest-ll-portfolio, invest-ll-execute,
   invest-ll-triggers...) y deja claro que ejecutarlo y confirmarlo es cosa del operador.
2. Nada de predicciones presentadas como fiables. Escenarios y analisis si; "va a subir" no.
   Ni tu ni nadie tiene ventaja predictiva demostrable sobre precios.
3. El win rate no es criterio de exito. Si sale el tema, recuerda expectancy y drawdown.
4. Los datos del contexto llevan fecha. Si estan viejos, dilo antes de usarlos.
5. Lo medido en este proyecto (21 anhos, decisiones reales): operar menos gano a operar mas
   (423 operaciones -> 2.890; una sola -> 37.773), y ninguna estrategia probada batio a comprar
   y mantener. No animes a operar; cada operacion son comisiones.
6. Si no sabes algo o el contexto no lo cubre, dilo. Inventar un dato aqui cuesta dinero real.
"""


class ChatUnavailableError(InvestLLError):
    """No se pudo hablar con el CLI de claude."""


class ChatSession:
    """Una conversación. El historial vive aquí; el contexto se reconstruye por mensaje."""

    __slots__ = ("_historial", "_model", "_runner")

    def __init__(
        self,
        *,
        model: str = MODELO_POR_DEFECTO,
        runner: Callable[[str], str] | None = None,
    ) -> None:
        self._model = model
        self._runner = runner
        self._historial: list[tuple[str, str]] = []

    @property
    def history(self) -> list[tuple[str, str]]:
        return list(self._historial)

    def build_prompt(self, pregunta: str, contexto: str) -> str:
        """El prompt completo. Separado de `ask` para poder probarlo sin gastar cuota."""
        bloques = [INSTRUCCIONES, "=== SITUACION ACTUAL ===", contexto]
        if self._historial:
            bloques.append("=== CONVERSACION HASTA AHORA ===")
            for autor, texto in self._historial[-MAX_TURNOS_EN_PROMPT:]:
                bloques.append(f"{autor}: {texto}")
        bloques.append(f"operador: {pregunta}")
        bloques.append("asistente:")
        return "\n\n".join(bloques)

    def ask(self, pregunta: str, *, contexto: str) -> str:
        prompt = self.build_prompt(pregunta, contexto)
        respuesta = (self._runner or self._llamar_cli)(prompt).strip()
        self._historial.append(("operador", pregunta))
        self._historial.append(("asistente", respuesta))
        return respuesta

    def _llamar_cli(self, prompt: str) -> str:
        try:
            proceso = subprocess.run(
                [
                    ejecutable() or EJECUTABLE,
                    "-p",
                    "--output-format",
                    "text",
                    "--disable-slash-commands",
                    "--model",
                    self._model,
                ],
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=TIMEOUT_SEGUNDOS,
                check=False,
            )
        except FileNotFoundError as error:
            raise ChatUnavailableError(
                f"no se encontro {EJECUTABLE!r} en el PATH; el chat usa el CLI de Claude "
                "con tu suscripcion, igual que invest-ll-generate"
            ) from error
        except subprocess.TimeoutExpired as error:
            raise ChatUnavailableError(f"claude no respondio en {TIMEOUT_SEGUNDOS}s") from error

        if proceso.returncode != 0:
            detalle = (proceso.stderr or proceso.stdout or "sin mensaje").strip()
            raise ChatUnavailableError(f"claude devolvio un error: {detalle[:300]}")
        return proceso.stdout

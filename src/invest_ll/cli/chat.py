"""`invest-ll-chat`: hablar con Claude desde la terminal, con tu cartera delante.

Interactivo por naturaleza: no lleva `--json` porque no produce un resultado que consumir, igual
que `invest-ll-panel`. Un agente que quiera datos tiene los nueve comandos con `--json`; esto es
para la persona.

Cada mensaje gasta cuota de tu suscripción, y el chat **no puede ejecutar nada**: propone
comandos y la confirmación sigue siendo tuya.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from invest_ll.chat.context import build_context
from invest_ll.chat.session import MODELO_POR_DEFECTO, ChatSession, ChatUnavailableError
from invest_ll.cli.compare import SALIDA_ERROR, SALIDA_OK

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

DESPEDIDAS = frozenset({"salir", "exit", "quit", "adios"})


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="invest-ll-chat",
        description=(
            "Chat con Claude sobre tu cartera y tus datos. Lee y explica; NO ejecuta nada. "
            "Cada mensaje gasta cuota de tu suscripcion."
        ),
    )
    parser.add_argument("--model", default=MODELO_POR_DEFECTO)
    args = parser.parse_args(argv)

    sesion = ChatSession(model=args.model)

    print("Chat de INVEST LL. Escribe 'salir' para terminar.")
    print("El chat lee tu cartera y tus datos; no puede ejecutar nada.")
    print("Cada mensaje gasta cuota de tu suscripcion de Claude.")

    while True:
        try:
            pregunta = input("\ntu> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return SALIDA_OK
        if not pregunta:
            continue
        if pregunta.lower() in DESPEDIDAS:
            return SALIDA_OK

        try:
            respuesta = sesion.ask(pregunta, contexto=build_context())
        except ChatUnavailableError as error:
            print(f"Error: {error}", file=sys.stderr)
            return SALIDA_ERROR

        print(f"\nclaude> {respuesta}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

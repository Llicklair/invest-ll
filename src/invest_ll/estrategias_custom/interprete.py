"""El intérprete de estrategias a medida: lo que conecta el formato con el motor de bots.

ESQUELETO DEL CONTRATO v4. Lo implementa el paquete de estrategias a medida; el motor de bots lo
llama para los bots con plantilla `medida`, igual que llama a `bots.decisiones` para las plantillas
de v3: misma `Situacion` de entrada y misma `Decision` de salida (órdenes con su porqué), solo con
velas cerradas.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.bots.decisiones import Decision, Situacion


def decidir(definicion: dict[str, Any], situacion: Situacion) -> Decision:
    """Lo que la estrategia `definicion` (ya validada) quiere hacer en esta situación."""
    raise NotImplementedError("pendiente de implementar")


def intervalo(definicion: dict[str, Any]) -> str:
    """El intervalo de velas con que decide la estrategia (p. ej. '1h')."""
    raise NotImplementedError("pendiente de implementar")


def monedas(definicion: dict[str, Any]) -> list[str]:
    """Las monedas que opera la estrategia."""
    raise NotImplementedError("pendiente de implementar")

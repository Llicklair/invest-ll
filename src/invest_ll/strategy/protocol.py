"""Contrato de las estrategias (T027).

Tipado estructural a propósito: cualquier objeto con `decide` sirve, herede de lo que herede.
Es lo que permite medir una regla fija y un modelo de IA con la misma vara (Principio V).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.engine.view import MarketView


class SignalKind(Enum):
    """Intenciones que una estrategia puede expresar. v1 no contempla posiciones cortas."""

    ENTER_LONG = "enter_long"
    EXIT = "exit"


@dataclass(frozen=True, slots=True)
class Signal:
    """Intención de operar, no una ejecución.

    Deliberadamente **sin cantidad ni precio**: el dimensionado es competencia del motor
    (FR-027). Si cada estrategia eligiera su tamaño, dos estrategias dejarían de ser
    comparables y el Principio V se caería.
    """

    kind: SignalKind
    stop_loss: float | None = None
    take_profit: float | None = None

    def __post_init__(self) -> None:
        for nombre in ("stop_loss", "take_profit"):
            valor: float | None = getattr(self, nombre)
            if valor is not None and valor <= 0:
                raise ValueError(f"{nombre} debe ser positivo, recibido {valor!r}")


@runtime_checkable
class Strategy(Protocol):
    """Lo único que el motor exige de una estrategia.

    Obligaciones de quien la implementa:

    - **No mirar al futuro**: usar solo lo que `view` ofrece. Intentar más lanza `LookAheadError`.
    - **Ser determinista**: misma vista, misma señal. Sin reloj, sin red, sin aleatoriedad sin
      semilla (FR-005).
    - **No dimensionar**: la señal expresa intención; el tamaño lo decide el motor.
    """

    def decide(self, view: MarketView) -> Signal | None:
        """Decide qué hacer tras el cierre del periodo actual. `None` es no hacer nada."""
        ...

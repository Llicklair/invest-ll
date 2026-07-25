"""Estrategias de juguete para los tests del motor.

Deterministas y triviales a propósito: cuando un test falla, el fallo es del motor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from invest_ll.strategy.protocol import Signal, SignalKind

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.engine.view import MarketView


class NuncaOpera:
    def decide(self, view: MarketView) -> Signal | None:
        return None


class AlternaCadaDosPeriodos:
    """Entra y sale alternativamente: genera muchas operaciones cortas."""

    def decide(self, view: MarketView) -> Signal | None:
        n = len(view)
        if n < 2:
            return None
        if n % 4 == 2:
            return Signal(kind=SignalKind.ENTER_LONG)
        if n % 4 == 0:
            return Signal(kind=SignalKind.EXIT)
        return None


class EntraYMantiene:
    """Entra en el segundo periodo y no vuelve a decidir nada."""

    def decide(self, view: MarketView) -> Signal | None:
        if len(view) == 2:
            return Signal(kind=SignalKind.ENTER_LONG)
        return None


class Tramposa:
    """Intenta leer el futuro. Debe provocar LookAheadError (SC-003)."""

    def decide(self, view: MarketView) -> Signal | None:
        futura = view.bar_at(-1)  # el periodo siguiente: no debería ser alcanzable
        actual = view.current_bar
        if futura.close > actual.close:
            return Signal(kind=SignalKind.ENTER_LONG)
        return Signal(kind=SignalKind.EXIT)

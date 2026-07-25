"""Ruptura de máximos: segunda estrategia de referencia (T044).

Existe para demostrar el Principio V: su mecanismo es distinto al del cruce de medias, se conecta
por el mismo protocolo, y añadirla no ha requerido tocar ni una línea del motor.

Igual que la otra, está aquí como caso de prueba honesto y no como recomendación: una ruptura
compra precisamente cuando el precio ya ha subido, así que paga el movimiento tarde y sufre
especialmente en mercados laterales, donde las rupturas falsas se encadenan.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from invest_ll.strategy.protocol import Signal, SignalKind

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.engine.view import MarketView


class BreakoutHighs:
    """Compra cuando el cierre supera el máximo de los últimos N periodos; sale bajo el mínimo."""

    __slots__ = ("_lookback",)

    def __init__(self, lookback: int = 20) -> None:
        if lookback < 2:
            raise ValueError("el lookback debe ser de al menos 2 periodos")
        self._lookback = lookback

    def decide(self, view: MarketView) -> Signal | None:
        if len(view) < self._lookback + 1:
            return None

        # El periodo actual se excluye de la referencia: compararlo consigo mismo no diría nada.
        ventana = view.closes(self._lookback + 1)[:-1]
        actual = float(view.current_bar.close)

        if actual > float(ventana.max()):
            return Signal(kind=SignalKind.ENTER_LONG)
        if actual < float(ventana.min()):
            return Signal(kind=SignalKind.EXIT)
        return None

    def __repr__(self) -> str:
        return f"BreakoutHighs(lookback={self._lookback})"

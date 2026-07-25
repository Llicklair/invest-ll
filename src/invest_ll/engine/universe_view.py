"""Vista de solo-pasado sobre varios activos.

El equivalente de `MarketView` cuando hay que comparar activos entre sí. Misma garantía y por el
mismo motivo: una estrategia de rotación necesita ver el pasado de todos los candidatos, y no
puede ver el futuro de ninguno.

Es especialmente fácil colar look-ahead aquí. Basta con preguntar "¿cuál subió más?" mirando un
tramo que incluya el día siguiente para construir una estrategia perfecta e imposible.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from invest_ll.errors import LookAheadError

if TYPE_CHECKING:  # pragma: no cover
    from datetime import datetime

    from invest_ll.data.bar import Bar
    from invest_ll.data.universe import Universe


class UniverseView:
    """Ventana de solo-pasado sobre un universo de activos."""

    __slots__ = ("_cursor", "_universe")

    def __init__(self, universe: Universe, cursor: int) -> None:
        if not 0 <= cursor < len(universe):
            raise IndexError(
                f"cursor {cursor} fuera del rango [0, {len(universe) - 1}] del universo"
            )
        self._universe = universe
        self._cursor = cursor

    @property
    def symbols(self) -> tuple[str, ...]:
        return self._universe.symbols

    @property
    def current_timestamp(self) -> datetime:
        return self._universe.timestamps[self._cursor]

    def __len__(self) -> int:
        """Periodos visibles, no la longitud real del universo."""
        return self._cursor + 1

    def current_bar(self, symbol: str) -> Bar:
        return self._universe.bar(symbol, self._cursor)

    def closes(self, symbol: str, periods: int) -> tuple[float, ...]:
        """Cierres recientes de un activo. Nunca posteriores al cursor."""
        return self._universe.closes_until(symbol, self._cursor, periods)

    def return_over(self, symbol: str, periods: int) -> float | None:
        """Rendimiento del activo en los últimos `periods` periodos.

        Devuelve `None` si no hay histórico suficiente, en lugar de calcularlo con menos datos de
        los pedidos: comparar un activo medido sobre 30 días con otro medido sobre 5 daría ventaja
        al segundo por puro azar de la ventana.
        """
        if periods < 1:
            raise ValueError(f"periods debe ser positivo, recibido {periods}")
        if len(self) < periods + 1:
            return None

        cierres = self.closes(symbol, periods + 1)
        if len(cierres) < periods + 1 or cierres[0] <= 0:
            return None
        return cierres[-1] / cierres[0] - 1.0

    def bar_at(self, symbol: str, offset: int) -> Bar:
        """Vela `offset` periodos hacia atrás. Un offset negativo apunta al futuro y falla."""
        if offset < 0:
            raise LookAheadError(
                f"acceso a datos futuros: offset={offset} sobre {symbol} apunta más allá de "
                f"{self.current_timestamp}. El backtest queda invalidado."
            )
        index = self._cursor - offset
        if index < 0:
            raise IndexError(f"offset {offset} queda antes del comienzo del universo")
        return self._universe.bar(symbol, index)

    def __repr__(self) -> str:
        return f"UniverseView(at={self.current_timestamp.isoformat()}, activos={len(self.symbols)})"

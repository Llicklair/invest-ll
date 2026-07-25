"""Estrategias de rotación: en qué activo estar en cada momento.

La idea del operador: en vez de acertar cuándo entrar y salir de un activo, estar siempre en el
que mejor va y saltar cuando otro lo adelanta.

Tiene más fundamento que el momentum sobre un solo activo — es de los pocos efectos que han
sobrevivido a décadas de escrutinio académico. Lo cual **no** significa que vaya a funcionar aquí:
significa que merece medirse en serio en lugar de descartarse.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.engine.universe_view import UniverseView


@runtime_checkable
class RotationStrategy(Protocol):
    """Decide en qué activo estar. `None` significa quedarse fuera del mercado."""

    def choose(self, view: UniverseView) -> str | None:
        """Activo en el que estar tras el cierre del periodo actual."""
        ...


class RelativeMomentum:
    """Estar en el activo que más ha subido en los últimos N periodos.

    `min_return` es el filtro que evita el error clásico de esta estrategia: sin él, cuando todos
    los activos caen la estrategia se queda en "el que menos cae" y pierde igual, solo que más
    despacio. Con `min_return=0` se sale del mercado si ninguno sube — que es justo lo que un
    seguidor de tendencia debería hacer en un mercado bajista general.
    """

    __slots__ = ("_lookback", "_min_return")

    def __init__(self, lookback: int = 90, *, min_return: float | None = 0.0) -> None:
        if lookback < 2:
            raise ValueError("el lookback necesita al menos 2 periodos")
        self._lookback = lookback
        self._min_return = min_return

    def choose(self, view: UniverseView) -> str | None:
        mejor: str | None = None
        mejor_rendimiento = float("-inf")

        for symbol in view.symbols:
            rendimiento = view.return_over(symbol, self._lookback)
            if rendimiento is None:
                continue
            if rendimiento > mejor_rendimiento:
                mejor_rendimiento = rendimiento
                mejor = symbol

        if mejor is None:
            return None
        if self._min_return is not None and mejor_rendimiento < self._min_return:
            # Ninguno sube lo suficiente: fuera del mercado. Quedarse en "el que menos cae" es
            # perder igual, solo que con la sensación de estar haciendo algo.
            return None
        return mejor

    def __repr__(self) -> str:
        return f"RelativeMomentum(lookback={self._lookback}, min_return={self._min_return})"


class AlwaysFirst:
    """Se queda siempre en el primer activo del universo.

    Existe como control: si una estrategia de rotación no bate a quedarse quieto en uno solo, no
    está aportando nada por mucho que se mueva.
    """

    __slots__ = ()

    def choose(self, view: UniverseView) -> str | None:
        return view.symbols[0]

    def __repr__(self) -> str:
        return "AlwaysFirst()"

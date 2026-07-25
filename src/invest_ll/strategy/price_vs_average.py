"""Precio contra su media: entrar por encima, salir al primer signo de debilidad.

La idea que describe el operador: sacar la media de los últimos N periodos, entrar cuando el
precio la supera y retirarse en cuanto asoma la bajada.

Se diferencia del cruce de medias en la reactividad. Comparar dos medias suaviza el ruido y llega
tarde a todo; comparar el precio contra una media reacciona de inmediato — para bien y para mal.

**La media se calcula solo con el pasado visible**, nunca sobre la serie entera. El `MarketView`
que recibe la estrategia no expone el futuro, así que ese error no se puede cometer aunque se
quiera. Es el Principio II funcionando.

**El coste de salir pronto**: cuanto antes se sale, más veces se sale por una oscilación normal
que no era el principio de nada. Cada una de esas falsas alarmas paga comisión y, si el precio
recupera, obliga a volver a entrar más caro. `exit_margin` existe para medir ese equilibrio en
lugar de suponerlo.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from invest_ll.strategy.protocol import Signal, SignalKind

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.engine.view import MarketView


class PriceVsAverage:
    """Compra por encima de la media móvil, vende por debajo.

    `exit_margin` es la holgura que se le da al precio antes de considerar que la bajada va en
    serio, expresada en tanto por uno sobre la media. Con `0` se sale al primer cierre por debajo
    — el "primer indicio" literal. Con `0.02` hay que caer un 2% bajo la media para salir, lo que
    ignora las oscilaciones pequeñas a cambio de reaccionar más tarde a las de verdad.
    """

    __slots__ = ("_exit_margin", "_periods")

    def __init__(self, periods: int = 30, *, exit_margin: float = 0.0) -> None:
        if periods < 2:
            raise ValueError("la media necesita al menos 2 periodos")
        if exit_margin < 0:
            raise ValueError("el margen de salida no puede ser negativo")
        self._periods = periods
        self._exit_margin = exit_margin

    def decide(self, view: MarketView) -> Signal | None:
        if len(view) < self._periods:
            return None

        media = float(view.closes(self._periods).mean())
        actual = float(view.current_bar.close)

        if actual > media:
            return Signal(kind=SignalKind.ENTER_LONG)
        if actual < media * (1 - self._exit_margin):
            return Signal(kind=SignalKind.EXIT)
        return None

    def __repr__(self) -> str:
        return f"PriceVsAverage(periods={self._periods}, exit_margin={self._exit_margin})"

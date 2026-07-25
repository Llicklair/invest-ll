"""Cruce de medias móviles: la estrategia de referencia (T034, FR-019).

Sirve para dos cosas: es la idea que el operador quiere probar, y es el caso de prueba que valida
el motor de extremo a extremo.

Los parámetros se expresan en **número de periodos**, no en días (FR-033). Así la misma estrategia
se puede evaluar sobre velas diarias, horarias o de un minuto sin tocar una línea.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from invest_ll.strategy.protocol import Signal, SignalKind

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.engine.view import MarketView


class MovingAverageCrossover:
    """Compra cuando la media corta cruza por encima de la larga, y sale cuando cruza por debajo.

    Nota sobre lo que esta estrategia **no** es: un cruce de medias es un indicador de tendencia
    con retraso estructural — reacciona después de que el movimiento haya empezado. Funciona en
    mercados con tendencia clara y produce muchas señales falsas en mercados laterales, donde las
    comisiones se comen el resultado. Está aquí como referencia honesta para validar el motor, no
    como una recomendación de inversión.
    """

    __slots__ = ("_long", "_short")

    def __init__(self, short: int = 10, long: int = 30) -> None:
        if short <= 0 or long <= 0:
            raise ValueError("los periodos deben ser positivos")
        if short >= long:
            raise ValueError(
                f"el periodo corto ({short}) debe ser menor que el largo ({long}); "
                "si no, no hay cruce que detectar"
            )
        self._short = short
        self._long = long

    def decide(self, view: MarketView) -> Signal | None:
        # Hace falta un periodo extra para saber dónde estaban las medias antes: sin eso se
        # detecta la posición relativa, no el cruce.
        if len(view) < self._long + 1:
            return None

        closes = view.closes(self._long + 1)

        corta_ahora = closes[-self._short :].mean()
        larga_ahora = closes[-self._long :].mean()
        corta_antes = closes[-self._short - 1 : -1].mean()
        larga_antes = closes[-self._long - 1 : -1].mean()

        cruce_alcista = corta_antes <= larga_antes and corta_ahora > larga_ahora
        cruce_bajista = corta_antes >= larga_antes and corta_ahora < larga_ahora

        if cruce_alcista:
            return Signal(kind=SignalKind.ENTER_LONG)
        if cruce_bajista:
            return Signal(kind=SignalKind.EXIT)
        return None

    def __repr__(self) -> str:
        return f"MovingAverageCrossover(short={self._short}, long={self._long})"

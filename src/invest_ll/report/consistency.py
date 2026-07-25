"""Consistencia: ¿con qué frecuencia se acaba el periodo en verde?

El resultado total no dice nada sobre el camino. Dos estrategias que ganan lo mismo pueden
haberlo hecho subiendo despacio y sin sobresaltos, o ganando mucho en dos meses y sangrando
el resto — y la segunda es imposible de aguantar sin abandonarla.

**Advertencia que acompaña siempre a estas cifras**: un porcentaje alto de meses positivos NO es
señal de una buena estrategia. Vender opciones, promediar a la baja o doblar tras cada pérdida
producen rachas larguísimas de meses en verde y luego lo devuelven todo de golpe. Por eso aquí se
reporta junto al peor mes: la pregunta no es solo cuántas veces ganas, sino qué pasa la vez que
pierdes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from itertools import pairwise


@dataclass(frozen=True, slots=True)
class Consistency:
    """Cómo de regular fue el camino, no solo dónde acabó."""

    periods: int
    positive_periods: int
    best_period: Decimal
    worst_period: Decimal
    longest_losing_streak: int

    @property
    def positive_ratio(self) -> float:
        """Proporción de meses acabados en verde."""
        if self.periods == 0:
            return 0.0
        return self.positive_periods / self.periods

    @property
    def asymmetry(self) -> Decimal:
        """Cuántas veces el peor mes es mayor que el mejor.

        Por encima de 1 significa que la peor caída supera a la mejor subida: el perfil de una
        estrategia que gana poco muchas veces y pierde mucho una. Es la cifra que desmonta un
        porcentaje de aciertos bonito.

        Devuelve 0 cuando **ningún** mes fue positivo. No significa "sin asimetría": significa que
        la comparación no aplica, porque no hubo ninguna subida con la que comparar la caída. En
        ese caso el porcentaje de meses en verde ya vale 0 y habla por sí solo.
        """
        if self.best_period <= 0:
            return Decimal(0)
        return abs(self.worst_period) / abs(self.best_period)


def monthly_consistency(
    equity_curve: Sequence[Decimal], timestamps: Sequence[datetime]
) -> Consistency:
    """Analiza la curva de patrimonio mes a mes.

    Se agrupa por mes natural en lugar de por bloques de N días porque es como el operador vive
    el resultado: mirando el saldo a fin de mes.
    """
    if len(equity_curve) < 2 or len(equity_curve) != len(timestamps):
        return Consistency(
            periods=0,
            positive_periods=0,
            best_period=Decimal(0),
            worst_period=Decimal(0),
            longest_losing_streak=0,
        )

    # Último valor de cada mes, en orden.
    cierres: list[Decimal] = []
    mes_actual = (timestamps[0].year, timestamps[0].month)
    ultimo = equity_curve[0]

    for valor, momento in zip(equity_curve, timestamps, strict=True):
        mes = (momento.year, momento.month)
        if mes != mes_actual:
            cierres.append(ultimo)
            mes_actual = mes
        ultimo = valor
    cierres.append(ultimo)

    if len(cierres) < 2:
        return Consistency(
            periods=0,
            positive_periods=0,
            best_period=Decimal(0),
            worst_period=Decimal(0),
            longest_losing_streak=0,
        )

    # Las variaciones van entre cierres de meses consecutivos. El primer mes se queda fuera a
    # propósito: no se conoce con qué saldo empezó, y meterlo comparándolo consigo mismo añadiría
    # un mes falso con resultado cero que ensucia el porcentaje.
    variaciones = [posterior - anterior for anterior, posterior in pairwise(cierres)]

    positivos = sum(1 for v in variaciones if v > 0)

    racha = 0
    peor_racha = 0
    for v in variaciones:
        if v < 0:
            racha += 1
            peor_racha = max(peor_racha, racha)
        else:
            racha = 0

    return Consistency(
        periods=len(variaciones),
        positive_periods=positivos,
        best_period=max(variaciones),
        worst_period=min(variaciones),
        longest_losing_streak=peor_racha,
    )

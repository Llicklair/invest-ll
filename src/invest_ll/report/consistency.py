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

from collections.abc import Callable, Sequence
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


def _mes(momento: datetime) -> tuple[int, int]:
    return (momento.year, momento.month)


def _semana(momento: datetime) -> tuple[int, int]:
    """Año y semana ISO. El año ISO no siempre coincide con el del calendario.

    Se usa el par completo y no solo el número: la semana 1 de 2026 empieza el 29 de diciembre de
    2025, así que agrupar por número suelto juntaría semanas separadas por un año entero.
    """
    natural = momento.isocalendar()
    return (natural.year, natural.week)


def _sin_datos() -> Consistency:
    return Consistency(
        periods=0,
        positive_periods=0,
        best_period=Decimal(0),
        worst_period=Decimal(0),
        longest_losing_streak=0,
    )


def monthly_consistency(
    equity_curve: Sequence[Decimal], timestamps: Sequence[datetime]
) -> Consistency:
    """Analiza la curva de patrimonio mes a mes.

    Se agrupa por mes natural en lugar de por bloques de N días porque es como el operador vive
    el resultado: mirando el saldo a fin de mes.
    """
    return _consistency_por(equity_curve, timestamps, clave=_mes)


def weekly_consistency(
    equity_curve: Sequence[Decimal], timestamps: Sequence[datetime]
) -> Consistency:
    """Analiza la curva de patrimonio semana a semana.

    Sirve para responder con datos a «pruebo una semana y veo»: una semana suelta es ruido, pero la
    distribución de **todas** las semanas dice cuántas acaban en verde y cuánto pesa la peor.

    Al ser periodos más cortos que el mes, el porcentaje en verde suele bajar y la asimetría se ve
    mejor: cuanto más se acorta la ventana, más manda el ruido y menos la estrategia.
    """
    return _consistency_por(equity_curve, timestamps, clave=_semana)


def _consistency_por(
    equity_curve: Sequence[Decimal],
    timestamps: Sequence[datetime],
    *,
    clave: Callable[[datetime], tuple[int, int]],
) -> Consistency:
    """Agrupa la curva por el periodo que devuelva `clave` y mide la regularidad.

    La granularidad se inyecta en lugar de duplicar el recorrido: mes y semana solo se diferencian
    en dónde ponen la frontera, y una segunda copia del cálculo acabaría divergiendo de la primera.
    """
    if len(equity_curve) < 2 or len(equity_curve) != len(timestamps):
        return _sin_datos()

    # Último valor de cada periodo, en orden.
    cierres: list[Decimal] = []
    periodo_actual = clave(timestamps[0])
    ultimo = equity_curve[0]

    for valor, momento in zip(equity_curve, timestamps, strict=True):
        periodo = clave(momento)
        if periodo != periodo_actual:
            cierres.append(ultimo)
            periodo_actual = periodo
        ultimo = valor
    cierres.append(ultimo)

    if len(cierres) < 2:
        return _sin_datos()

    # Las variaciones van entre cierres de periodos consecutivos. El primero se queda fuera a
    # propósito: no se conoce con qué saldo empezó, y meterlo comparándolo consigo mismo añadiría
    # un periodo falso con resultado cero que ensucia el porcentaje.
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

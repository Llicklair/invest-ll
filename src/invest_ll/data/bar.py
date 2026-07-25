"""Bar e Interval: la unidad mínima de la serie histórica (T014).

La validación vive en el constructor a propósito. Una vela incoherente no debe poder existir en
memoria: si se rechaza aquí, ningún cálculo posterior necesita volver a comprobarla.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from invest_ll.errors import InvalidSeriesError


class Interval(Enum):
    """Duración de un periodo. El motor es agnóstico a cuál se use (FR-032)."""

    MINUTE_1 = timedelta(minutes=1)
    MINUTE_5 = timedelta(minutes=5)
    MINUTE_15 = timedelta(minutes=15)
    HOUR_1 = timedelta(hours=1)
    HOUR_4 = timedelta(hours=4)
    DAY_1 = timedelta(days=1)

    @property
    def duration(self) -> timedelta:
        return self.value


def _check_price(name: str, value: float) -> None:
    if math.isnan(value) or math.isinf(value):
        raise InvalidSeriesError(f"{name} no es un número finito: {value!r}")
    if value <= 0:
        raise InvalidSeriesError(f"{name} debe ser positivo, recibido {value!r}")


@dataclass(frozen=True, slots=True)
class Bar:
    """Observación de un periodo de mercado.

    `timestamp` marca el **inicio** del periodo. La vela se considera cerrada cuando el motor
    avanza más allá de ella: es esa distinción la que impide decidir con un cierre que aún no ha
    ocurrido.
    """

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise InvalidSeriesError(
                f"timestamp sin zona horaria: {self.timestamp!r}. "
                "En bolsa la zona determina si el mercado estaba abierto."
            )

        for name in ("open", "high", "low", "close"):
            _check_price(name, getattr(self, name))

        if math.isnan(self.volume) or math.isinf(self.volume):
            raise InvalidSeriesError(f"volume no es un número finito: {self.volume!r}")
        if self.volume < 0:
            raise InvalidSeriesError(f"volume no puede ser negativo: {self.volume!r}")

        if self.high < self.low:
            raise InvalidSeriesError(f"high ({self.high}) es menor que low ({self.low})")
        if not (self.low <= self.open <= self.high):
            raise InvalidSeriesError(
                f"open ({self.open}) fuera del rango [{self.low}, {self.high}]"
            )
        if not (self.low <= self.close <= self.high):
            raise InvalidSeriesError(
                f"close ({self.close}) fuera del rango [{self.low}, {self.high}]"
            )

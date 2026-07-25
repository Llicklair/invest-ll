"""PriceSeries: la serie histórica validada (T016).

Precomputa los arrays numpy que el bucle necesita. La validación es total y ocurre una sola vez:
a partir de aquí, el motor puede confiar en los datos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np

from invest_ll.errors import InvalidSeriesError

if TYPE_CHECKING:  # pragma: no cover
    from numpy.typing import NDArray

    from invest_ll.data.bar import Bar, Interval
    from invest_ll.data.calendars import MarketCalendar

# Tolerancia al comparar marcas con el intervalo declarado. Absorbe el redondeo de segundos de
# algunos proveedores sin dejar pasar una vela realmente descolocada.
_TOLERANCIA_SEGUNDOS = 1.0

# Tolerancia adicional para series de un día o más.
#
# Los proveedores de bolsa fechan las velas diarias con la hora local del mercado, y esa hora se
# desplaza cuando el país cambia al horario de verano. El fin de semana del cambio, dos velas
# consecutivas quedan a 71 horas en vez de 72 y dejan de ser múltiplo del intervalo.
#
# No es un dato corrupto: es el reloj del proveedor. Una hora de desviación en una serie diaria
# solo puede ser eso. En intradía no se aplica, porque ahí una hora de diferencia sí significa que
# la vela está donde no debe.
_TOLERANCIA_DST_SEGUNDOS = 3600.0
_UN_DIA_SEGUNDOS = 86400.0


@dataclass(frozen=True, slots=True)
class PriceSeries:
    """Serie histórica de un activo, validada y lista para simular."""

    symbol: str
    interval: Interval
    calendar: MarketCalendar
    bars: tuple[Bar, ...]

    opens: NDArray[np.float64] = field(init=False, repr=False)
    highs: NDArray[np.float64] = field(init=False, repr=False)
    lows: NDArray[np.float64] = field(init=False, repr=False)
    closes: NDArray[np.float64] = field(init=False, repr=False)
    timestamps: tuple[datetime, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.bars:
            raise InvalidSeriesError("la serie está vacía")

        self._validate_chronology()

        object.__setattr__(self, "opens", np.array([b.open for b in self.bars], dtype=np.float64))
        object.__setattr__(self, "highs", np.array([b.high for b in self.bars], dtype=np.float64))
        object.__setattr__(self, "lows", np.array([b.low for b in self.bars], dtype=np.float64))
        object.__setattr__(self, "closes", np.array([b.close for b in self.bars], dtype=np.float64))
        object.__setattr__(self, "timestamps", tuple(b.timestamp for b in self.bars))

    def _validate_chronology(self) -> None:
        step = self.interval.duration.total_seconds()
        tolerancia = _TOLERANCIA_DST_SEGUNDOS if step >= _UN_DIA_SEGUNDOS else _TOLERANCIA_SEGUNDOS

        for previous, current in zip(self.bars, self.bars[1:], strict=False):
            delta = (current.timestamp - previous.timestamp).total_seconds()

            if delta <= 0:
                raise InvalidSeriesError(
                    f"orden cronológico roto: {previous.timestamp} → {current.timestamp}"
                )

            # Un múltiplo exacto del intervalo es un hueco (lo clasifica el loader contra el
            # calendario). Un resto distinto de cero significa una vela desalineada: la serie
            # no es del intervalo que dice ser.
            resto = delta % step
            if min(resto, step - resto) > tolerancia:
                raise InvalidSeriesError(
                    f"marca no alineada al intervalo {self.interval.name}: "
                    f"{current.timestamp} está a {delta}s de la anterior"
                )

    def __len__(self) -> int:
        return len(self.bars)

    def __getitem__(self, index: int) -> Bar:
        return self.bars[index]

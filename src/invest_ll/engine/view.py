"""MarketView: la barrera del Principio II (T017).

El fichero más importante del proyecto, y deliberadamente pequeño: cuanto menos código tenga,
más fácil es convencerse de que el invariante se cumple.

**El invariante**: una estrategia no puede obtener datos posteriores al periodo que se está
simulando. No porque se le pida que no lo haga, sino porque la interfaz que recibe no ofrece
ninguna vía para conseguirlo.

**El límite honesto**: Python no tiene encapsulación real. Una estrategia decidida a hacer trampa
puede alcanzar `_series` por introspección. Esta clase no es un sandbox y no pretende serlo. La
garantía es de superficie pública, y por eso el diseño la complementa con el test de la estrategia
tramposa (SC-003) en lugar de descansar solo en ella.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from invest_ll.errors import LookAheadError

if TYPE_CHECKING:  # pragma: no cover
    from datetime import datetime

    import numpy as np
    from numpy.typing import NDArray

    from invest_ll.data.bar import Bar
    from invest_ll.data.series import PriceSeries


class MarketView:
    """Ventana de solo-pasado sobre una serie histórica.

    `cursor` apunta al último periodo **cerrado**. Todo lo que hay más allá existe en memoria
    pero es inalcanzable desde aquí.
    """

    __slots__ = ("_cursor", "_series")

    def __init__(self, series: PriceSeries, cursor: int) -> None:
        if not 0 <= cursor < len(series):
            raise IndexError(f"cursor {cursor} fuera del rango [0, {len(series) - 1}] de la serie")
        self._series = series
        self._cursor = cursor

    # --- Estado visible -------------------------------------------------

    @property
    def current_timestamp(self) -> datetime:
        """Marca del último periodo cerrado."""
        return self._series.timestamps[self._cursor]

    @property
    def current_bar(self) -> Bar:
        """Último periodo cerrado. La vela en curso no es visible."""
        return self._series.bars[self._cursor]

    def __len__(self) -> int:
        """Número de periodos visibles, no la longitud real de la serie."""
        return self._cursor + 1

    # --- Acceso al pasado -----------------------------------------------

    def bar_at(self, offset: int) -> Bar:
        """Periodo situado `offset` posiciones hacia atrás. `offset=0` es el actual.

        Un `offset` negativo apunta al futuro: en lugar de devolver el dato, falla. Es el punto
        donde el Principio II se hace visible como comportamiento y no como documentación.
        """
        if offset < 0:
            raise LookAheadError(
                f"acceso a datos futuros: offset={offset} apunta más allá de "
                f"{self.current_timestamp}. El backtest queda invalidado."
            )
        index = self._cursor - offset
        if index < 0:
            raise IndexError(
                f"offset {offset} queda antes del comienzo de la serie "
                f"({len(self)} periodos disponibles)"
            )
        return self._series.bars[index]

    def history(self, periods: int) -> tuple[Bar, ...]:
        """Los `periods` periodos más recientes ya cerrados, en orden cronológico.

        Si hay menos de los pedidos, devuelve los que hay. **Nunca rellena**: un hueco debe
        notarse, no taparse con datos inventados.
        """
        start = self._slice_start(periods)
        return self._series.bars[start : self._cursor + 1]

    def closes(self, periods: int) -> NDArray[np.float64]:
        """Precios de cierre del pasado reciente, listos para calcular indicadores.

        El array se devuelve **de solo lectura**. Un slice de numpy es una vista sobre el buffer
        original: sin esto, una estrategia podría escribir en él y alterar la serie histórica que
        ven las demás. No sería mirar al futuro, sería reescribir el pasado — y el determinismo
        de FR-005 se caería sin que nada fallara de forma visible.
        """
        start = self._slice_start(periods)
        ventana = self._series.closes[start : self._cursor + 1].view()
        ventana.flags.writeable = False
        return ventana

    def _slice_start(self, periods: int) -> int:
        if periods <= 0:
            raise ValueError(f"periods debe ser positivo, recibido {periods}")
        return max(0, self._cursor - periods + 1)

    def __repr__(self) -> str:
        return f"MarketView(at={self.current_timestamp.isoformat()}, visible={len(self)})"

"""Universo: varias series alineadas en el tiempo para poder rotar entre ellas.

Rotar significa estar siempre en el activo que mejor va. Para decidirlo hay que comparar varios
activos **en el mismo instante**, y eso exige que sus series estén alineadas.

Tres decisiones gobiernan este módulo, y las tres existen para no mentir:

1. **Solo se usan las fechas comunes a todos los activos.** Un activo que no cotizó ese día no
   puede compararse con los que sí. Rellenar su precio con el del día anterior inventaría un dato
   y falsearía la comparación.

2. **El universo se fija de antemano y no cambia.** Añadir un activo a mitad del histórico —o
   quitarlo cuando empieza a ir mal— es la forma más rápida de construir un backtest ganador y
   falso.

3. **El sesgo de selección se advierte siempre.** Elegir hoy qué activos rotar es elegirlos
   sabiendo cuáles subieron. Ningún backtest de rotación puede corregir eso, y fingir que no
   existe sería la clase de garantía falsa que la constitución prohíbe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from invest_ll.errors import InvalidSeriesError

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

    from invest_ll.data.bar import Bar, Interval
    from invest_ll.data.series import PriceSeries

MINIMO_ACTIVOS = 2


@dataclass(frozen=True, slots=True)
class Universe:
    """Conjunto de activos alineados sobre las fechas que todos comparten."""

    symbols: tuple[str, ...]
    interval: Interval
    timestamps: tuple[datetime, ...]
    bars_by_symbol: dict[str, tuple[Bar, ...]] = field(repr=False)

    def __len__(self) -> int:
        return len(self.timestamps)

    def bar(self, symbol: str, index: int) -> Bar:
        return self.bars_by_symbol[symbol][index]

    def closes_until(self, symbol: str, index: int, periods: int) -> tuple[float, ...]:
        """Cierres del activo hasta `index` incluido, como mucho `periods`.

        Nunca devuelve nada posterior a `index`: es la misma garantía que da `MarketView` para un
        solo activo, extendida a varios (Principio II).
        """
        if periods <= 0:
            raise ValueError(f"periods debe ser positivo, recibido {periods}")
        inicio = max(0, index - periods + 1)
        return tuple(bar.close for bar in self.bars_by_symbol[symbol][inicio : index + 1])


def common_range(
    series: Sequence[PriceSeries],
) -> tuple[datetime, datetime, str, str]:
    """Rango que comparten todos los activos, y quién marca cada extremo.

    Si el inicio sale posterior al final, no hay solape — y los dos nombres devueltos son
    exactamente los dos activos que lo impiden.
    """
    ultimo_inicio = max(series, key=lambda s: s.timestamps[0])
    primer_final = min(series, key=lambda s: s.timestamps[-1])
    return (
        ultimo_inicio.timestamps[0],
        primer_final.timestamps[-1],
        ultimo_inicio.symbol,
        primer_final.symbol,
    )


def _explicar_sin_solape(series: Sequence[PriceSeries]) -> str:
    """Mensaje que dice qué activos chocan y qué hacer al respecto.

    Listar los rangos de todos obliga a compararlos a ojo. Nombrar a los dos culpables y proponer
    una salida convierte el error en algo accionable.
    """
    inicio, fin, quien_empieza, quien_acaba = common_range(series)

    detalle = "\n".join(
        f"    {s.symbol}: {s.timestamps[0].date()} a {s.timestamps[-1].date()}" for s in series
    )
    return (
        f"los activos no comparten ninguna fecha. {quien_empieza} no tiene datos hasta "
        f"{inicio.date()}, pero {quien_acaba} se acaba en {fin.date()}: no hay ni un dia en que "
        f"todos coticen a la vez.\n"
        f"  Rangos disponibles:\n{detalle}\n"
        f"  Salidas: quita {quien_empieza} o {quien_acaba} de la seleccion, o amplia su descarga "
        f"con invest-ll-fetch para que se solapen."
    )


def build_universe(series: Sequence[PriceSeries]) -> Universe:
    """Alinea varias series sobre las fechas que todas comparten.

    Se descartan las fechas en las que falta algún activo. Es deliberadamente estricto: comparar
    el rendimiento de un activo que cotizó con el de otro que no habría cotizado ese día no
    compara nada.
    """
    if len(series) < MINIMO_ACTIVOS:
        raise InvalidSeriesError(
            f"un universo necesita al menos {MINIMO_ACTIVOS} activos para poder rotar entre ellos"
        )

    intervalos = {s.interval for s in series}
    if len(intervalos) > 1:
        raise InvalidSeriesError(
            f"todos los activos deben tener el mismo intervalo, hay {len(intervalos)} distintos"
        )

    simbolos = [s.symbol for s in series]
    if len(set(simbolos)) != len(simbolos):
        raise InvalidSeriesError(f"hay activos repetidos en el universo: {simbolos}")

    comunes = set(series[0].timestamps)
    for otra in series[1:]:
        comunes &= set(otra.timestamps)

    if not comunes:
        raise InvalidSeriesError(_explicar_sin_solape(series))

    fechas = tuple(sorted(comunes))
    por_simbolo: dict[str, tuple[Bar, ...]] = {}
    for una in series:
        indice = {bar.timestamp: bar for bar in una.bars}
        por_simbolo[una.symbol] = tuple(indice[fecha] for fecha in fechas)

    return Universe(
        symbols=tuple(simbolos),
        interval=series[0].interval,
        timestamps=fechas,
        bars_by_symbol=por_simbolo,
    )

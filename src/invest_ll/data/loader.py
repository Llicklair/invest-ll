"""Carga de series desde disco (T018).

Los avisos se **devuelven** junto a la serie en lugar de escribirse en un log. Un log se ignora;
un valor de retorno hay que recibirlo, y de ahí acaba en el informe (FR-016).

Nota sobre tipos: este módulo y `calendars.py` son la frontera con pandas y exchange_calendars,
que no publican tipado completo. La comprobación estricta se relaja **solo aquí**; el motor, el
informe y las estrategias siguen en modo estricto, que es donde un error de tipos costaría dinero.
"""

# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false, reportMissingTypeStubs=false

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from invest_ll.data.bar import Bar
from invest_ll.data.series import PriceSeries
from invest_ll.errors import InvalidSeriesError

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.data.bar import Interval
    from invest_ll.data.calendars import MarketCalendar

from datetime import timedelta

COLUMNAS = ("timestamp", "open", "high", "low", "close", "volume")
_UN_DIA = timedelta(days=1)
_PRECIOS = ("open", "high", "low", "close", "volume")


@dataclass(frozen=True, slots=True)
class DataWarning:
    """Anomalía detectada en los datos que no impide simular, pero el operador debe conocer."""

    message: str
    at: datetime | None = None


def load_series(
    path: Path,
    *,
    symbol: str,
    interval: Interval,
    calendar: MarketCalendar,
) -> tuple[PriceSeries, tuple[DataWarning, ...]]:
    """Lee un CSV o Parquet y devuelve la serie validada junto a sus avisos."""
    import pandas as pd

    if not path.exists():
        raise FileNotFoundError(f"no existe el fichero de serie: {path}")

    suffix = path.suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(path)
    elif suffix in {".parquet", ".pq"}:
        frame = pd.read_parquet(path)
    else:
        raise InvalidSeriesError(
            f"formato no soportado: extensión {suffix!r}. Se admiten .csv y .parquet"
        )

    faltan = [c for c in COLUMNAS if c not in frame.columns]
    if faltan:
        raise InvalidSeriesError(f"columna(s) ausente(s) en {path.name}: {', '.join(faltan)}")

    if len(frame) == 0:
        raise InvalidSeriesError(f"el fichero {path.name} no contiene ninguna vela")

    aviso_zona = _detectar_columna_sin_zona(frame["timestamp"], path.name)

    marcas: list[datetime] = [
        ts.to_pydatetime() for ts in pd.to_datetime(frame["timestamp"], utc=True, format="mixed")
    ]

    valores: dict[str, np.ndarray] = {
        nombre: frame[nombre].to_numpy(dtype=np.float64) for nombre in _PRECIOS
    }

    bars = tuple(
        Bar(
            timestamp=marcas[i],
            open=float(valores["open"][i]),
            high=float(valores["high"][i]),
            low=float(valores["low"][i]),
            close=float(valores["close"][i]),
            volume=float(valores["volume"][i]),
        )
        for i in range(len(marcas))
    )

    series = PriceSeries(symbol=symbol, interval=interval, calendar=calendar, bars=bars)
    avisos = ((aviso_zona,) if aviso_zona is not None else ()) + detect_gaps(series)
    return series, avisos


def _detectar_columna_sin_zona(columna: Any, nombre_fichero: str) -> DataWarning | None:
    """¿La columna de timestamps original no llevaba zona horaria?

    `pd.to_datetime(..., utc=True)` relabela en silencio cualquier marca naive como UTC. Eso es
    correcto para los CSV que el propio proyecto escribe (siempre con zona), pero un CSV de
    terceros con horas locales (p.ej. hora de Nueva York sin offset) se carga como si fueran UTC
    sin que nadie lo note. No se rechaza — hay CSV legítimos escritos a mano sin zona, sobre todo
    en cripto — mas hay que decirlo, porque la diferencia horaria falsea que velas se consideran
    negociables y que huecos se reportan.
    """
    import pandas as pd

    try:
        sin_forzar = pd.to_datetime(columna, format="mixed")
    except ValueError:
        # Mezcla de valores con y sin zona en la misma columna: al menos una parte SI la llevaba,
        # no es el caso "csv enteramente naive" que nos interesa avisar aqui.
        return None

    tz = getattr(sin_forzar.dtype, "tz", None)
    if tz is not None:
        return None

    return DataWarning(
        message=(
            f"{nombre_fichero}: los timestamps no llevan zona horaria; se ha asumido UTC. "
            "Si las horas del fichero eran locales (no UTC), las velas negociables y los huecos "
            "detectados seran erroneos."
        )
    )


def detect_gaps(series: PriceSeries) -> tuple[DataWarning, ...]:
    """Clasifica cada salto: cierre legítimo del mercado o dato ausente (FR-021).

    La diferencia importa. En bolsa, la noche y los festivos son huecos normales; reportarlos
    como anomalía ahogaría los avisos de verdad entre ruido.
    """
    step = series.interval.duration
    avisos: list[DataWarning] = []

    # Misma distinción que en el motor: para velas de un día o más la pregunta es si hubo sesión,
    # no si el mercado estaba abierto en ese instante concreto. Con velas diarias fechadas a
    # medianoche, `is_open` diría siempre que no y ningún hueco se reportaría jamás.
    negociable = series.calendar.is_session if step >= _UN_DIA else series.calendar.is_open

    for previous, current in zip(series.bars, series.bars[1:], strict=False):
        if current.timestamp - previous.timestamp <= step:
            continue

        # Hay salto: ¿el mercado operaba en algún momento del hueco?
        momento = previous.timestamp + step
        while momento < current.timestamp:
            if negociable(momento):
                avisos.append(
                    DataWarning(
                        message=(
                            f"hueco de datos: falta la vela de {momento.isoformat()} "
                            "con el mercado abierto"
                        ),
                        at=momento,
                    )
                )
                break
            momento += step

    return tuple(avisos)

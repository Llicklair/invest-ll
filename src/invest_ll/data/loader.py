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
from typing import TYPE_CHECKING

import numpy as np

from invest_ll.data.bar import Bar
from invest_ll.data.series import PriceSeries
from invest_ll.errors import InvalidSeriesError

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.data.bar import Interval
    from invest_ll.data.calendars import MarketCalendar

COLUMNAS = ("timestamp", "open", "high", "low", "close", "volume")
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
    return series, detect_gaps(series)


def detect_gaps(series: PriceSeries) -> tuple[DataWarning, ...]:
    """Clasifica cada salto: cierre legítimo del mercado o dato ausente (FR-021).

    La diferencia importa. En bolsa, la noche y los festivos son huecos normales; reportarlos
    como anomalía ahogaría los avisos de verdad entre ruido.
    """
    step = series.interval.duration
    avisos: list[DataWarning] = []

    for previous, current in zip(series.bars, series.bars[1:], strict=False):
        if current.timestamp - previous.timestamp <= step:
            continue

        # Hay salto: ¿el mercado estuvo abierto en algún momento del hueco?
        momento = previous.timestamp + step
        while momento < current.timestamp:
            if series.calendar.is_open(momento):
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

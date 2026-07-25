"""Persistencia del histórico (T017).

Dos decisiones gobiernan este módulo:

1. **El CSV tiene exactamente las columnas que el loader de la 001 ya espera.** Por eso la
   procedencia va en un fichero hermano y no dentro del propio CSV: meterla ahí obligaría a
   cabeceras extra y rompería la compatibilidad que hace innecesaria cualquier conversión.
2. **La escritura es atómica.** Se escribe un temporal en el mismo directorio y se renombra. Una
   descarga interrumpida deja como mucho un temporal huérfano, nunca un CSV a medias que el motor
   aceptaría como histórico completo.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from invest_ll.data.bar import Bar
from invest_ll.data.calendars import Continuous24x7, ExchangeCalendarAdapter
from invest_ll.data.series import PriceSeries
from invest_ll.fetch.provenance import Provenance
from invest_ll.fetch.request import FetchRequest, Market

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

CABECERA = "timestamp,open,high,low,close,volume\n"
DEFAULT_ROOT = Path("data/market")


class HistoryStore:
    """Almacén de históricos en disco.

    Disposición: `<raiz>/<proveedor>/<activo>/<intervalo>.csv` más su `.meta.json` hermano, y
    `discrepancias/` para las versiones en conflicto que nunca se aplican solas.
    """

    __slots__ = ("_root",)

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or DEFAULT_ROOT

    # --- Rutas ----------------------------------------------------------

    def directory(self, request: FetchRequest, provider: str) -> Path:
        return self._root / provider / request.path_key

    def csv_path(self, request: FetchRequest, provider: str) -> Path:
        return self.directory(request, provider) / f"{request.interval.name}.csv"

    def meta_path(self, request: FetchRequest, provider: str) -> Path:
        return self.directory(request, provider) / f"{request.interval.name}.meta.json"

    # --- Lectura --------------------------------------------------------

    def load(self, request: FetchRequest, provider: str) -> tuple[PriceSeries, Provenance] | None:
        """Lo almacenado, o `None` si aún no hay nada.

        Devuelve `None` en lugar de lanzar: que no exista todavía es el caso normal la primera
        vez, no un error.
        """
        csv = self.csv_path(request, provider)
        meta = self.meta_path(request, provider)
        if not csv.exists() or not meta.exists():
            return None

        bars: list[Bar] = []
        for linea in csv.read_text(encoding="utf-8").splitlines()[1:]:
            if not linea.strip():
                continue
            ts, o, h, low, c, v = linea.split(",")
            bars.append(
                Bar(
                    timestamp=datetime.fromisoformat(ts),
                    open=float(o),
                    high=float(h),
                    low=float(low),
                    close=float(c),
                    volume=float(v),
                )
            )
        if not bars:
            return None

        series = PriceSeries(
            symbol=request.symbol,
            interval=request.interval,
            calendar=calendar_for(request),
            bars=tuple(bars),
        )
        return series, Provenance.from_json(meta.read_text(encoding="utf-8"))

    # --- Escritura ------------------------------------------------------

    def save(self, request: FetchRequest, series: PriceSeries, provenance: Provenance) -> Path:
        """Guarda serie y procedencia de forma atómica."""
        directorio = self.directory(request, provenance.provider)
        directorio.mkdir(parents=True, exist_ok=True)

        csv = self.csv_path(request, provenance.provider)
        write_atomic(csv, CABECERA + "".join(_as_row(bar) for bar in series.bars))
        write_atomic(self.meta_path(request, provenance.provider), provenance.to_json())
        return csv

    def save_discrepancies(
        self,
        request: FetchRequest,
        provider: str,
        bars: Sequence[Bar],
        at: datetime,
    ) -> Path:
        """Guarda aparte la versión en conflicto (FR-026).

        No sustituye a nada: el histórico local sigue intacto. Queda ahí para que el operador
        pueda comparar y decidir, que es suyo y no del sistema.
        """
        directorio = self.directory(request, provider) / "discrepancias"
        directorio.mkdir(parents=True, exist_ok=True)
        marca = at.strftime("%Y%m%dT%H%M%S")
        destino = directorio / f"{request.interval.name}-{marca}.csv"
        write_atomic(destino, CABECERA + "".join(_as_row(bar) for bar in bars))
        return destino


def calendar_for(request: FetchRequest) -> Continuous24x7 | ExchangeCalendarAdapter:
    """El calendario que corresponde al mercado del activo."""
    if request.market is Market.CRYPTO:
        return Continuous24x7()
    return ExchangeCalendarAdapter("XNYS")


def _as_row(bar: Bar) -> str:
    return f"{bar.timestamp.isoformat()},{bar.open},{bar.high},{bar.low},{bar.close},{bar.volume}\n"


def write_atomic(destino: Path, contenido: str) -> None:
    """Escribe mediante temporal + renombrado.

    El temporal va en el **mismo directorio** a propósito: cruzar sistemas de ficheros convertiría
    el renombrado en una copia, y una copia no es atómica. `os.replace` sí lo es, y en Windows
    además sobrescribe sin quejarse.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, temporal = tempfile.mkstemp(dir=destino.parent, prefix=".tmp-", suffix=destino.suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fichero:
            fichero.write(contenido)
        # PTH105 sugiere Path.replace(). Se mantiene os.replace() a proposito: es el punto
        # exacto donde la operacion se vuelve atomica y el test de atomicidad lo sustituye para
        # simular un corte. Envolverlo en Path lo esconde sin ganar nada.
        os.replace(temporal, destino)  # noqa: PTH105
    except BaseException:
        Path(temporal).unlink(missing_ok=True)
        raise

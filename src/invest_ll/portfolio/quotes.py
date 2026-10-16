"""El último precio descargado de un activo, **siempre con su fecha**.

Con históricos parados desde hace semanas, un valor sin fecha parecería de hoy — y eso es mentir.
Por eso `ultimo_cierre` devuelve el par (precio, fecha) y nunca el precio suelto.

Se lee el histórico COMPLETO, ignorando la reserva de datos: la reserva protege lo que se mide
(los backtests), no lo que se mira. Valorar la cartera con el precio de hace año y medio sin
decirlo sería el mismo fallo que ya tuvo el panel.

No toca la red: solo lo que ya está en `data/market/`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from invest_ll.dashboard.data import RAIZ_DATOS, discover_assets
from invest_ll.errors import InvestLLError

if TYPE_CHECKING:  # pragma: no cover
    from datetime import datetime
    from pathlib import Path

    from invest_ll.data.bar import Bar


def ultimo_cierre(symbol: str, data_root: Path = RAIZ_DATOS) -> tuple[Decimal, datetime] | None:
    """El último cierre descargado y la fecha de esa vela. `None` si no hay datos del activo."""
    velas = _velas(symbol, data_root)
    if velas is None:
        return None
    ultima = velas[-1]
    return _decimal(ultima.close), ultima.timestamp


def maximo_y_ultimo(symbol: str, data_root: Path = RAIZ_DATOS) -> tuple[Decimal, Decimal] | None:
    """El cierre máximo de todo el histórico descargado y el último. `None` si no hay datos.

    Cierres y no máximos intradía: es la misma vara que la columna "desde máximo" del panel, y
    un pico de minutos no es un precio al que se pudiera haber vendido con calma.
    """
    velas = _velas(symbol, data_root)
    if velas is None:
        return None
    return _decimal(max(v.close for v in velas)), _decimal(velas[-1].close)


def _velas(symbol: str, data_root: Path) -> tuple[Bar, ...] | None:
    """Las velas del histórico más reciente del activo, entre todos los descargados.

    Si el mismo activo está descargado de varios proveedores o intervalos, se usa el que llega más
    lejos en el tiempo (y, a igualdad, el de más historia): el precio más fresco que hay. Un
    histórico que no se puede leer se salta — mostrar "sin datos" es honesto; inventar, no.
    """
    buscado = symbol.strip().upper()
    mejor: tuple[Bar, ...] | None = None
    for activo in discover_assets(data_root):
        if activo.symbol.upper() != buscado:
            continue
        try:
            velas = activo.load_completa().bars
        except (InvestLLError, OSError, ValueError, KeyError):
            # Un historico ilegible equivale a no tenerlo: quien llama dira "sin datos".
            continue
        if not velas:
            continue
        if mejor is None or (velas[-1].timestamp, len(velas)) > (mejor[-1].timestamp, len(mejor)):
            mejor = velas
    return mejor


def _decimal(precio: float) -> Decimal:
    """De float a Decimal por su representación corta: 80.0 -> 80.0, no 80.000000000000003."""
    return Decimal(repr(precio))

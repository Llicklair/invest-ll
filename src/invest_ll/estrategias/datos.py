"""Los paneles de precios que usan las estrategias, leídos del disco una vez por versión.

Dos ficheros, los que escribe `invest-ll-quant download`:

- cripto: `data/market/binance-universe/klines_1d.parquet` (todos los pares USDT de Binance, los
  que ya no cotizan incluidos);
- bolsa: `data/market/etf-universe/etf_1d.parquet` (los ocho fondos del estudio más SHY).

Leerlos tarda (el de Binance son decenas de MB), así que se guardan en memoria con la **huella**
del fichero como clave: ruta, fecha de modificación y tamaño. Una descarga nueva cambia la huella y
se vuelve a leer; nunca se sirve un panel viejo. No toca la red: si falta un fichero, se dice qué
comando lo trae.

Aquí vive también `cierre`: el último precio de un activo, con su fecha, mirando tanto los
históricos sueltos de `data/market/<proveedor>/` como estos paneles, y quedándose con el más
reciente. Valorar la cartera necesita las dos fuentes: un fondo comprado con el plan (IEF) solo
está en el panel de ETF, y una moneda de la cesta, solo en el de Binance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

import numpy as np

from invest_ll.nombres import base, es_cripto
from invest_ll.portfolio.quotes import ultimo_cierre

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.quant.panel import Panel

Mercado = Literal["bolsa", "cripto"]

FICHEROS: Final[dict[Mercado, Path]] = {
    "cripto": Path("data/market/binance-universe/klines_1d.parquet"),
    "bolsa": Path("data/market/etf-universe/etf_1d.parquet"),
}
COMANDOS: Final[dict[Mercado, str]] = {
    "cripto": "uv run invest-ll-quant download",
    "bolsa": "uv run invest-ll-quant download --etf",
}
DESCRIPCION: Final[dict[Mercado, str]] = {
    "cripto": "los datos de Binance",
    "bolsa": "los datos de los fondos",
}

Huella = tuple[str, int, int]


def huella(mercado: Mercado) -> Huella | None:
    """(ruta absoluta, modificación en ns, tamaño) del fichero; `None` si no está descargado."""
    fichero = FICHEROS[mercado]
    if not fichero.exists():
        return None
    estado = fichero.stat()
    return (str(fichero.resolve()), estado.st_mtime_ns, estado.st_size)


def motivo_sin_datos(mercado: Mercado) -> str:
    return f"Faltan {DESCRIPCION[mercado]}. Descárgalos con: {COMANDOS[mercado]}"


@lru_cache(maxsize=4)
def _leer(mercado: Mercado, clave: Huella) -> Panel:
    """El panel de ese fichero en esa versión. `clave` solo indexa la caché."""
    ruta = clave[0]
    if mercado == "cripto":
        from invest_ll.quant.panel import load_binance_universe

        return load_binance_universe(ruta)
    from invest_ll.quant.etf_study import load_etf_panel

    return load_etf_panel(ruta)


def panel(mercado: Mercado) -> Panel | None:
    """El panel descargado de ese mercado; `None` si no hay fichero."""
    clave = huella(mercado)
    return None if clave is None else _leer(mercado, clave)


def precio_legible(valor: float) -> Decimal:
    """Un precio del panel con 8 cifras significativas: 90.42 y no 90.41999816894531.

    Los paneles guardan precios en coma flotante (y los de ETF, ajustados), así que su `repr`
    arrastra decimales que nadie pagó. Ocho cifras significativas sobran para un precio de
    referencia y no se comen los decimales de una moneda que vale 0,0000123.
    """
    return Decimal(f"{valor:.8g}")


@dataclass(frozen=True, slots=True)
class Cierre:
    precio: Decimal
    fecha: date


def cierre_en_panel(p: Panel, simbolo: str) -> Cierre | None:
    """El último cierre válido del instrumento de `p` que corresponde a `simbolo`.

    Acepta `SPY`, `BTC/USDT` o `BTCUSDT`. Si un ticker se reutilizó (`LUNAUSDT`, `LUNAUSDT~2`), vale
    el instrumento que cotizó más tarde: es la moneda que existe hoy con ese nombre.
    """
    mejor = _columna(p, simbolo)
    if mejor is None:
        return None
    fila = int(p.last_valid[mejor])
    valor = float(p.close[fila, mejor])
    if not np.isfinite(valor) or valor <= 0:
        return None
    return Cierre(precio=precio_legible(valor), fecha=p.date_at(fila))


def _columna(p: Panel, simbolo: str) -> int | None:
    """La columna del instrumento de `simbolo` que cotizó más tarde, o `None`."""
    buscado = base(simbolo)
    columnas = [
        i
        for i, s in enumerate(p.symbols)
        if (s == simbolo.upper() or p.bases[i].upper() == buscado) and int(p.last_valid[i]) >= 0
    ]
    return max(columnas, key=lambda i: int(p.last_valid[i])) if columnas else None


def cierre_hasta(simbolo: str, fecha: date) -> Cierre | None:
    """El último cierre del panel de su mercado en `fecha` o antes (el precio de ese día)."""
    p = panel("cripto" if es_cripto(simbolo) else "bolsa")
    if p is None:
        return None
    col = _columna(p, simbolo)
    if col is None:
        return None
    fila = min(p.index_of(fecha + timedelta(days=1)) - 1, int(p.last_valid[col]))
    while fila >= 0 and not np.isfinite(p.close[fila, col]):
        fila -= 1
    if fila < 0:
        return None
    return Cierre(precio=precio_legible(float(p.close[fila, col])), fecha=p.date_at(fila))


@dataclass(frozen=True, slots=True)
class Variacion:
    simbolo: str
    precio: float
    fecha: date
    var_1m: float | None
    """En %: 4.6 es un +4,6 % en el último mes."""


def variacion_del_mes(simbolo: str) -> Variacion | None:
    """El último cierre y cuánto cambió en 30 días, del panel de su mercado."""
    p = panel("cripto" if es_cripto(simbolo) else "bolsa")
    if p is None:
        return None
    col = _columna(p, simbolo)
    if col is None:
        return None
    fila = int(p.last_valid[col])
    ultimo = float(p.close[fila, col])
    fecha = p.date_at(fila)
    antes = p.index_of(fecha - timedelta(days=30))
    previo = float(p.close[antes, col]) if antes < fila else float("nan")
    var = (ultimo / previo - 1) * 100 if np.isfinite(previo) and previo > 0 else None
    return Variacion(simbolo=simbolo, precio=ultimo, fecha=fecha, var_1m=var)


def cierre(simbolo: str) -> Cierre | None:
    """El último precio conocido de un activo y su fecha, de la fuente más reciente.

    `None` si no hay datos en ningún sitio: quien valora dirá "sin precio", no inventará uno.
    """
    candidatos: list[Cierre] = []
    suelto = ultimo_cierre(simbolo)
    if suelto is not None:
        candidatos.append(Cierre(precio=suelto[0], fecha=suelto[1].date()))
    for mercado in FICHEROS:
        if mercado == "cripto" and not es_cripto(simbolo):
            continue
        if mercado == "bolsa" and es_cripto(simbolo):
            continue
        p = panel(mercado)
        if p is not None:
            en_panel = cierre_en_panel(p, simbolo)
            if en_panel is not None:
                candidatos.append(en_panel)
    if not candidatos:
        return None
    return max(candidatos, key=lambda c: c.fecha)

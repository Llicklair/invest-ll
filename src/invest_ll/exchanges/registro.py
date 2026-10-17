"""Dónde se piden los conectores. **Un solo sitio** (como `live/factory.py` para Binance en v2).

Lo usan los bots reales (para ejecutar), las pruebas de estrategias sobre el pasado (para las
velas) y Ajustes → Conexiones (para probar claves).

- `conector(exchange, red)`: con claves, para operar. Antes de darlo comprueba **otra vez** los
  cerrojos de `activacion` (activo en esa red, claves de ahora probadas, evidencia, permisos): lo
  que vale es el estado de cuando se pide, no el de cuando se activó.
- `conector_publico(exchange)`: sin claves, solo datos públicos (mercados, precio, libro, velas).
  Se guarda uno por exchange: cargar los mercados cuesta.
- `con_claves(exchange, red, claves)`: para probar unas claves antes de activar nada.

**Pruebas**: `inyectar(exchange, conector)` (o `with inyectados({...})`) sustituye la construcción
del conector de ccxt por uno falso (`falso.ConectorFalso`) para ese exchange, en todas sus redes y
en el público. Los cerrojos se siguen comprobando: un test de bots reales que pida `conector(x,
"real")` necesita lo mismo que en la realidad (o sustituir esta función entera).
"""

from __future__ import annotations

import hashlib
import threading
from contextlib import contextmanager
from typing import TYPE_CHECKING, Final

from invest_ll.exchanges import activacion, red_ccxt
from invest_ll.exchanges.ccxt_conector import ConectorCcxt
from invest_ll.exchanges.conector import ExchangeError
from invest_ll.exchanges.fichas import FICHAS, POR_ID

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Generator, Mapping

    from invest_ll.exchanges.conector import Conector, Red
    from invest_ll.exchanges.credenciales import ClavesExchange
    from invest_ll.exchanges.fichas import Ficha

REDES: Final[tuple[Red, ...]] = ("pruebas", "real")

_cerrojo = threading.Lock()
_inyectados: dict[str, Conector] = {}
_publicos: dict[str, Conector] = {}
_con_claves: dict[tuple[str, Red, str], Conector] = {}


def disponibles() -> list[str]:
    """Los ids de los exchanges que se pueden conectar ('binance', 'hyperliquid', …)."""
    return [f.id for f in FICHAS]


def ficha(exchange: str) -> Ficha:
    """La ficha del exchange. `ExchangeError` en llano si no se conoce."""
    encontrada = POR_ID.get(exchange)
    if encontrada is None:
        raise ExchangeError(
            f"No se conoce el exchange {exchange!r}. Los que hay: {', '.join(disponibles())}."
        )
    return encontrada


def conector(exchange: str, red: Red) -> Conector:
    """El conector con claves de ese exchange y red (para operar). `ExchangeError` en llano si no
    está conectado en esa red."""
    f = ficha(exchange)
    if red not in REDES:
        raise ExchangeError(f"Red desconocida {red!r}: 'pruebas' o 'real'.")
    estado = activacion.leer(f)
    faltan = activacion.por_que_no(estado, red)
    if faltan:
        raise ExchangeError(" ".join(faltan))
    claves = estado.claves[red]
    if claves is None:  # pragma: no cover - por_que_no ya lo exige
        raise ExchangeError(f"Faltan las claves de {f.nombre}.")
    return con_claves(exchange, red, claves)


def con_claves(exchange: str, red: Red, claves: ClavesExchange) -> Conector:
    """Un conector con esas claves, sin mirar si el exchange está activo: para probarlas.

    Se guarda uno por exchange, red y claves (en memoria), para no cargar los mercados en cada
    orden; si las claves cambian, es otro.
    """
    f = ficha(exchange)
    with _cerrojo:
        inyectado = _inyectados.get(exchange)
        if inyectado is not None:
            return inyectado
        clave = (exchange, red, _huella_en_memoria(claves))
        hecho = _con_claves.get(clave)
        if hecho is None:
            ex = red_ccxt.construir(f, red, claves.valores)
            hecho = ConectorCcxt(ex, f, red, claves=claves.valores)
            _con_claves[clave] = hecho
        return hecho


def conector_publico(exchange: str) -> Conector:
    """Un conector sin claves, solo para datos públicos (mercados, precio, libro, velas)."""
    f = ficha(exchange)
    with _cerrojo:
        inyectado = _inyectados.get(exchange)
        if inyectado is not None:
            return inyectado
        hecho = _publicos.get(exchange)
        if hecho is None:
            hecho = ConectorCcxt(red_ccxt.construir(f, "real", None), f, "real")
            _publicos[exchange] = hecho
        return hecho


def _huella_en_memoria(claves: ClavesExchange) -> str:
    texto = "\0".join(f"{k}={v}" for k, v in sorted(claves.valores.items()))
    return hashlib.sha256(texto.encode()).hexdigest()


# -- Para las pruebas ------------------------------------------------------------------------------


def inyectar(exchange: str, conector_falso: Conector) -> None:
    """Desde ahora, ese exchange da este conector (en todas sus redes y en el público)."""
    ficha(exchange)
    with _cerrojo:
        _inyectados[exchange] = conector_falso


def quitar_inyectados() -> None:
    """Vuelve a construir los conectores de verdad y olvida los que se habían guardado."""
    with _cerrojo:
        _inyectados.clear()
        _publicos.clear()
        _con_claves.clear()


@contextmanager
def inyectados(falsos: Mapping[str, Conector]) -> Generator[None]:
    """`with inyectados({"binance": falso}): ...` — y al salir, como estaba."""
    for exchange, falso in falsos.items():
        inyectar(exchange, falso)
    try:
        yield
    finally:
        with _cerrojo:
            for exchange in falsos:
                _inyectados.pop(exchange, None)

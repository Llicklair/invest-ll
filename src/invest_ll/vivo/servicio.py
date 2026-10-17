"""El servicio en vivo del panel: la conexión con Hyperliquid y la cuenta de práctica.

`crear_app(en_vivo=True)` (solo el lanzador del panel; nunca los tests) llama a `arrancar()` al
empezar y a `parar()` al terminar. `fuente()` da la fuente de precios en vivo a quien la necesite
(la cuenta de práctica, el motor de bots, las rutas de `/api/vivo`).

- `arrancar()` abre la conexión en segundo plano (`vivo/red.py`, el único módulo que sale a la red)
  y un bucle que ejecuta las órdenes con límite de la cuenta de práctica cuando el libro las cruza.
  No espera a la red: vuelve enseguida y los datos van llegando.
- Sin `arrancar()` (los tests, la generación del contrato) la fuente existe pero nunca se conecta:
  dice que no hay datos en vivo y no inventa ninguno.
- **Para las pruebas**: `usar_fuente(FuenteFalsa(...))` pone la fuente que se quiera (y
  `usar_fuente(None)` la quita); `revisar_ordenes()` hace a mano una vuelta del bucle de órdenes.

La cuenta de práctica vive en `practica/`, relativa al directorio de trabajo como el resto de datos
del panel; `cuenta()` la carga la primera vez (y otra vez si el directorio cambia, como en los tests).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from invest_ll.vivo.hyperliquid import FuenteHyperliquid
from invest_ll.vivo.mercado import como_mercado
from invest_ll.vivo.practica import CARPETA, CuentaDePractica

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.vivo.fuente import FuentePrecios
    from invest_ll.vivo.mercado import Mercado
    from invest_ll.vivo.practica import Ejecutada
    from invest_ll.vivo.red import ConexionHyperliquid

log = logging.getLogger(__name__)

AVISO_SIN_PANEL: Final = "Los precios en vivo solo llegan con el panel arrancado (invest-ll-panel)."
CADA_REVISION: Final = 0.25
"""Segundos entre dos repasos de las órdenes con límite (el libro llega cada ~0,5 s)."""

_cerrojo = threading.Lock()
_fuente: FuentePrecios | None = None
_conexion: ConexionHyperliquid | None = None
_bucle_ordenes: asyncio.Task[None] | None = None
_cuenta: CuentaDePractica | None = None


async def arrancar() -> None:
    """Abre la conexión con Hyperliquid y empieza a mantener los precios al día."""
    global _fuente, _conexion, _bucle_ordenes
    from invest_ll.vivo.red import ConexionHyperliquid

    nueva = FuenteHyperliquid()
    with _cerrojo:
        _fuente = nueva
    _conexion = ConexionHyperliquid(nueva)
    await _conexion.arrancar()
    for coin in cuenta().monedas_con_ordenes():
        nueva.seguir(coin, libro=True)
    _bucle_ordenes = asyncio.create_task(_repasar_ordenes(), name="practica-ordenes")


async def parar() -> None:
    """Cierra la conexión y deja todo guardado (la cuenta se guarda en cada operación)."""
    global _conexion, _bucle_ordenes
    if _bucle_ordenes is not None:
        _bucle_ordenes.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _bucle_ordenes
        _bucle_ordenes = None
    if _conexion is not None:
        await _conexion.parar()
        _conexion = None


def fuente() -> FuentePrecios:
    """La fuente de precios en vivo del proceso."""
    global _fuente
    with _cerrojo:
        if _fuente is None:
            _fuente = FuenteHyperliquid(aviso_inicial=AVISO_SIN_PANEL)
        return _fuente


def usar_fuente(nueva: FuentePrecios | None) -> None:
    """Pone la fuente de precios del proceso (las pruebas, una `FuenteFalsa`); `None` la quita y
    la siguiente vez se crea la de siempre, sin conexión."""
    global _fuente
    with _cerrojo:
        _fuente = nueva


def mercado() -> Mercado:
    """La fuente con lo que además enseña Operar (lista de monedas, operaciones, estado)."""
    return como_mercado(fuente())


def cuenta() -> CuentaDePractica:
    """La cuenta de práctica de `practica/` (en el directorio de trabajo de ahora)."""
    global _cuenta
    carpeta = CARPETA.resolve()
    with _cerrojo:
        if _cuenta is None or _cuenta.carpeta != carpeta:
            _cuenta = CuentaDePractica(carpeta)
        return _cuenta


def revisar_ordenes() -> list[Ejecutada]:
    """Ejecuta las órdenes con límite que el libro de ahora cruza (una vuelta del bucle)."""
    return cuenta().revisar(fuente())


def ahora() -> datetime:
    """La hora de las respuestas que no traen la suya. Las pruebas la fijan."""
    return datetime.now(UTC)


async def _repasar_ordenes() -> None:
    while True:
        try:
            if cuenta().monedas_con_ordenes():
                await asyncio.to_thread(revisar_ordenes)
        except Exception:  # un fallo aquí no puede parar el bucle: se cuenta y se sigue
            log.exception("No se pudieron repasar las órdenes con límite de la cuenta de práctica")
        await asyncio.sleep(CADA_REVISION)

"""La conexión con Hyperliquid: **el único módulo de `vivo` que sale a la red**.

`tests/unit/test_no_network_in_suite.py` lo vigila: cualquier otro módulo del paquete que importe un
cliente de red falla. Aquí solo hay transporte; lo que significan los mensajes y dónde se guardan
está en `vivo/hyperliquid.py`, que se prueba sin red.

- **WebSocket** (`wss://api.hyperliquid.xyz/ws`): `allMids` siempre; libro (`l2Book`, el rápido y
  el hondo), operaciones (`trades`) y velas (`candle`) de lo que se pide con
  `FuenteHyperliquid.seguir`.
  Reconecta solo, con espera creciente (1 s, 2 s, 4 s… hasta 30 s), y al volver lo pide todo otra
  vez. Un latido (`{"method": "ping"}`) cada 20 s, y si pasan 30 s sin ningún mensaje la conexión se
  da por muerta y se rehace.
- **REST** (`POST https://api.hyperliquid.xyz/info`): `metaAndAssetCtxs` cada minuto (decimales,
  precio de hace 24 h, volumen) y `candleSnapshot` para el histórico de cada serie de velas al
  seguirla y para tapar el hueco tras un corte. Como mucho 3 a la vez: Hyperliquid limita por IP
  (1200 de peso por minuto; estas pesan 20).

Nada espera a la red fuera de este módulo: todo corre en tareas de fondo del bucle del panel.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

import httpx
import websockets

from invest_ll.vivo.hyperliquid import (
    PETICION_META,
    PETICION_MIDS,
    URL_INFO,
    URL_WS,
    MensajeRaroError,
    mensaje_suscripcion,
    peticion_velas,
)

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Coroutine
    from contextlib import AbstractAsyncContextManager

    from websockets.asyncio.client import ClientConnection

    from invest_ll.vivo.hyperliquid import FuenteHyperliquid, Suscripcion

log = logging.getLogger(__name__)

ESPERA_INICIAL: Final = 1.0
ESPERA_MAXIMA: Final = 30.0
ESTABLE: Final = 60.0
"""Una conexión que aguantó esto vuelve a empezar la espera por 1 s si se corta."""
LATIDO: Final = 20.0
SILENCIO_MAXIMO: Final = 30.0
CADA_META: Final = 60.0
REINTENTO_REST: Final = 10.0
TIMEOUT_REST: Final = 15.0
RELLENOS_A_LA_VEZ: Final = 3
REPASO: Final = 5.0
"""Cada cuánto se repasa lo pedido aunque nadie avise (un relleno que falló, una moneda que
esperaba a la lista)."""

ERRORES_DE_RED = (OSError, TimeoutError, websockets.WebSocketException, httpx.HTTPError)


class ConexionHyperliquid:
    """Mantiene una `FuenteHyperliquid` al día. `arrancar` y `parar`, desde el bucle del panel.

    `conectar` (el `websockets.connect` de siempre) y `transporte` (el de httpx) solo se cambian en
    las pruebas, para hacer de Hyperliquid sin red.
    """

    def __init__(
        self,
        fuente: FuenteHyperliquid,
        *,
        url_ws: str = URL_WS,
        url_info: str = URL_INFO,
        conectar: Callable[..., AbstractAsyncContextManager[Any]] = websockets.connect,
        transporte: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._fuente = fuente
        self._url_ws = url_ws
        self._url_info = url_info
        self._conectar = conectar
        self._transporte = transporte
        self._bucle: asyncio.AbstractEventLoop | None = None
        self._aviso_ws = asyncio.Event()
        self._aviso_rellenos = asyncio.Event()
        self._tareas: list[asyncio.Task[None]] = []
        self._rellenos: set[asyncio.Task[None]] = set()
        self._http: httpx.AsyncClient | None = None

    async def arrancar(self) -> None:
        self._bucle = asyncio.get_running_loop()
        self._http = httpx.AsyncClient(timeout=TIMEOUT_REST, transport=self._transporte)
        self._fuente.al_seguir = self._avisar
        self._tareas = [
            self._tarea(self._bucle_ws(), "hyperliquid-ws"),
            self._tarea(self._bucle_meta(), "hyperliquid-meta"),
            self._tarea(self._bucle_rellenos(), "hyperliquid-velas"),
        ]

    async def parar(self) -> None:
        self._fuente.al_seguir = None
        tareas = [*self._tareas, *self._rellenos]
        for tarea in tareas:
            tarea.cancel()
        await asyncio.gather(*tareas, return_exceptions=True)
        self._tareas.clear()
        self._rellenos.clear()
        if self._http is not None:
            await self._http.aclose()
            self._http = None
        self._fuente.cerrada("el panel se ha cerrado")

    def _tarea(self, corrutina: Coroutine[Any, Any, None], nombre: str) -> asyncio.Task[None]:
        return asyncio.create_task(corrutina, name=nombre)

    def _avisar(self) -> None:
        """Hay algo nuevo que pedir. Se llama desde cualquier hilo (las rutas corren en otros)."""
        bucle = self._bucle
        if bucle is None or bucle.is_closed():
            return
        bucle.call_soon_threadsafe(self._aviso_ws.set)
        bucle.call_soon_threadsafe(self._aviso_rellenos.set)

    # -- REST --------------------------------------------------------------------------------------

    async def _info(self, cuerpo: dict[str, Any]) -> Any:
        assert self._http is not None
        respuesta = await self._http.post(self._url_info, json=cuerpo)
        respuesta.raise_for_status()
        return respuesta.json()

    async def _bucle_meta(self) -> None:
        primera = True
        while True:
            try:
                if primera:
                    self._fuente.recibir_mids(await self._info(PETICION_MIDS))
                self._fuente.recibir_meta(await self._info(PETICION_META))
                primera = False
                espera = CADA_META
            except (*ERRORES_DE_RED, MensajeRaroError, ValueError) as error:
                log.warning(
                    "No se pudo pedir la lista de monedas a Hyperliquid: %s", _motivo(error)
                )
                espera = REINTENTO_REST
            await asyncio.sleep(espera)

    async def _bucle_rellenos(self) -> None:
        limite = asyncio.Semaphore(RELLENOS_A_LA_VEZ)
        while True:
            self._aviso_rellenos.clear()
            for coin, intervalo, desde in self._fuente.por_rellenar():
                tarea = self._tarea(
                    self._rellenar(limite, coin, intervalo, desde), f"velas-{coin}-{intervalo}"
                )
                self._rellenos.add(tarea)
                tarea.add_done_callback(self._rellenos.discard)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._aviso_rellenos.wait(), timeout=REPASO)

    async def _rellenar(
        self, limite: asyncio.Semaphore, coin: str, intervalo: str, desde: datetime
    ) -> None:
        async with limite:
            pedidas_en = self._fuente.marca()
            try:
                datos = await self._info(peticion_velas(coin, intervalo, desde, datetime.now(UTC)))
                if not isinstance(datos, list):
                    raise MensajeRaroError("candleSnapshot no devolvió una lista")
                self._fuente.recibir_velas(coin, intervalo, datos, pedidas_en=pedidas_en)  # pyright: ignore[reportUnknownArgumentType]
            except (*ERRORES_DE_RED, MensajeRaroError, ValueError) as error:
                log.warning(
                    "No se pudo pedir el histórico de %s %s: %s", coin, intervalo, _motivo(error)
                )
                await asyncio.sleep(REINTENTO_REST)
                self._fuente.volver_a_rellenar(coin, intervalo)

    # -- WebSocket ---------------------------------------------------------------------------------

    async def _bucle_ws(self) -> None:
        espera = ESPERA_INICIAL
        while True:
            empezo = asyncio.get_running_loop().time()
            try:
                async with self._conectar(
                    self._url_ws, ping_interval=None, open_timeout=15, close_timeout=2
                ) as ws:
                    self._fuente.abierta()
                    self._aviso_rellenos.set()  # tapar el hueco del corte
                    await self._atender(ws)
                motivo = "Hyperliquid cerró la conexión"
            except ERRORES_DE_RED as error:
                motivo = _motivo(error)
            self._fuente.cerrada(motivo)
            if asyncio.get_running_loop().time() - empezo > ESTABLE:
                espera = ESPERA_INICIAL
            log.warning("Sin conexión con Hyperliquid (%s); se reintenta en %.0f s", motivo, espera)
            await asyncio.sleep(espera * (1 + random.random() / 5))
            espera = min(espera * 2, ESPERA_MAXIMA)

    async def _atender(self, ws: ClientConnection) -> None:
        """Lee, late y suscribe a la vez; en cuanto una de las tres acaba (un corte), acaban todas."""
        tareas = [
            self._tarea(self._leer(ws), "hyperliquid-leer"),
            self._tarea(self._latir(ws), "hyperliquid-latir"),
            self._tarea(self._suscribir(ws), "hyperliquid-suscribir"),
        ]
        try:
            hechas, _ = await asyncio.wait(tareas, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for tarea in tareas:
                tarea.cancel()
            await asyncio.gather(*tareas, return_exceptions=True)
        for tarea in hechas:
            error = tarea.exception()
            if error is not None:
                raise error

    async def _leer(self, ws: ClientConnection) -> None:
        while True:
            crudo = await asyncio.wait_for(ws.recv(), timeout=SILENCIO_MAXIMO)
            try:
                mensaje = json.loads(crudo)
            except ValueError:
                log.warning("Mensaje de Hyperliquid que no es JSON: %s", str(crudo)[:200])
                continue
            if isinstance(mensaje, dict):
                self._fuente.recibir(mensaje)  # pyright: ignore[reportUnknownArgumentType]

    async def _latir(self, ws: ClientConnection) -> None:
        while True:
            await asyncio.sleep(LATIDO)
            await ws.send(json.dumps({"method": "ping"}))

    async def _suscribir(self, ws: ClientConnection) -> None:
        enviadas: set[Suscripcion] = set()
        while True:
            self._aviso_ws.clear()
            for suscripcion in self._fuente.suscripciones():
                if suscripcion not in enviadas:
                    await ws.send(json.dumps(mensaje_suscripcion(suscripcion)))
                    enviadas.add(suscripcion)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._aviso_ws.wait(), timeout=REPASO)


def _motivo(error: BaseException) -> str:
    texto = str(error).strip()
    return f"{type(error).__name__}: {texto[:200]}" if texto else type(error).__name__

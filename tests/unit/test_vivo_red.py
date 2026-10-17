"""La conexión con Hyperliquid, contra un Hyperliquid de mentira: sin red.

El WebSocket es un objeto que entrega mensajes reales guardados y apunta lo que se le manda; el
REST, un `httpx.MockTransport`. Se comprueba lo que la conexión promete: pide la lista al arrancar,
se suscribe a lo seguido solo cuando la moneda existe, rellena el histórico de velas, reconecta
sola tras un corte y vuelve a pedirlo todo, y al pararla no deja nada en marcha.

El bucle de asyncio se crea con el socket real puesto un momento (los bucles abren un par de
sockets locales para despertarse; ver tests/integration/conftest.py): durante las pruebas el
bloqueo de red sigue en pie.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import websockets

from invest_ll.vivo import red
from invest_ll.vivo.hyperliquid import FuenteHyperliquid
from invest_ll.vivo.red import ConexionHyperliquid

from ..fixtures.vivo import bucle, mensaje

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Coroutine, Iterator

CORTE = object()


class WsFalso:
    """Un WebSocket de Hyperliquid de mentira: da lo que se le pone y apunta lo que se le manda."""

    def __init__(self, mensajes: list[dict[str, Any]]) -> None:
        self.cola: asyncio.Queue[object] = asyncio.Queue()
        for m in mensajes:
            self.cola.put_nowait(json.dumps(m))
        self.enviados: list[dict[str, Any]] = []

    async def __aenter__(self) -> WsFalso:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def recv(self) -> object:
        siguiente = await self.cola.get()
        if siguiente is CORTE:
            raise websockets.ConnectionClosedError(None, None)
        return siguiente

    async def send(self, texto: str) -> None:
        self.enviados.append(json.loads(texto))

    def suscripciones(self) -> list[dict[str, Any]]:
        return [e["subscription"] for e in self.enviados if e.get("method") == "subscribe"]


class Hyperliquid:
    """Las conexiones que se van abriendo y las peticiones REST que llegan."""

    def __init__(self) -> None:
        self.conexiones: list[WsFalso] = []
        self.peticiones: list[dict[str, Any]] = []

    def conectar(self, url: str, **_: object) -> WsFalso:
        assert url == red.URL_WS
        ws = WsFalso([mensaje("ws_allMids.json")])
        self.conexiones.append(ws)
        return ws

    def responder(self, peticion: httpx.Request) -> httpx.Response:
        cuerpo = json.loads(peticion.content)
        self.peticiones.append(cuerpo)
        respuestas = {
            "allMids": mensaje("rest_allMids.json"),
            "metaAndAssetCtxs": mensaje("rest_metaAndAssetCtxs.json"),
            "candleSnapshot": mensaje("rest_candleSnapshot_1m.json"),
        }
        return httpx.Response(200, json=respuestas[cuerpo["type"]])


@pytest.fixture
def correr() -> Iterator[Callable[[Coroutine[Any, Any, None]], None]]:
    with bucle() as runner:
        yield runner.run


@pytest.fixture(autouse=True)
def rapido(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(red, "ESPERA_INICIAL", 0.01)
    monkeypatch.setattr(red, "REPASO", 0.02)


async def hasta(condicion: Callable[[], bool], segundos: float = 3.0) -> None:
    limite = asyncio.get_running_loop().time() + segundos
    while not condicion():
        assert asyncio.get_running_loop().time() < limite, "no pasó a tiempo"
        await asyncio.sleep(0.01)


def test_arranca_sigue_reconecta_y_para(
    correr: Callable[[Coroutine[Any, Any, None]], None],
) -> None:
    hyperliquid = Hyperliquid()
    fuente = FuenteHyperliquid()

    async def prueba() -> None:
        conexion = ConexionHyperliquid(
            fuente,
            conectar=hyperliquid.conectar,
            transporte=httpx.MockTransport(hyperliquid.responder),
        )
        await conexion.arrancar()
        await hasta(lambda: fuente.conectada() and fuente.existe("BTC") is True)
        primera = hyperliquid.conexiones[0]
        assert primera.suscripciones() == [{"type": "allMids"}]
        assert [p["type"] for p in hyperliquid.peticiones] == ["allMids", "metaAndAssetCtxs"]

        # Seguir una moneda (como haría una ruta, desde otro hilo) la suscribe y trae su histórico.
        await asyncio.to_thread(fuente.seguir, "BTC", libro=True, intervalos=["1m"])
        await asyncio.to_thread(fuente.seguir, "NOEXISTE", libro=True)
        await hasta(lambda: len(primera.suscripciones()) == 5)
        assert primera.suscripciones()[1:] == [
            {"type": "l2Book", "coin": "BTC", "fast": True},
            {"type": "l2Book", "coin": "BTC"},
            {"type": "trades", "coin": "BTC"},
            {"type": "candle", "coin": "BTC", "interval": "1m"},
        ]
        await hasta(lambda: len(fuente.velas("BTC", "1m")) == 5)
        primera.cola.put_nowait(json.dumps(mensaje("ws_l2Book.json")))
        await hasta(lambda: fuente.libro("BTC") is not None)

        # Un corte: lo dice, reconecta solo y vuelve a pedirlo todo, con el hueco de velas.
        primera.cola.put_nowait(CORTE)
        await hasta(lambda: len(hyperliquid.conexiones) == 2)
        segunda = hyperliquid.conexiones[1]
        await hasta(lambda: len(segunda.suscripciones()) == 5)
        await hasta(fuente.conectada)
        await hasta(
            lambda: len([p for p in hyperliquid.peticiones if p["type"] == "candleSnapshot"]) == 2
        )
        velas = [p for p in hyperliquid.peticiones if p["type"] == "candleSnapshot"]
        assert velas[1]["req"]["startTime"] == 1792256580000  # desde la última que había

        await conexion.parar()
        assert not fuente.conectada()
        assert fuente.al_seguir is None
        pendientes = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        assert pendientes == []

    correr(prueba())


def test_sin_red_lo_dice_y_reintenta(
    correr: Callable[[Coroutine[Any, Any, None]], None],
) -> None:
    intentos: list[str] = []

    def sin_red(url: str, **_: object) -> WsFalso:
        intentos.append(url)
        raise OSError("sin red")

    def rest_caido(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red")

    fuente = FuenteHyperliquid()

    async def prueba() -> None:
        conexion = ConexionHyperliquid(
            fuente, conectar=sin_red, transporte=httpx.MockTransport(rest_caido)
        )
        await conexion.arrancar()
        await hasta(lambda: len(intentos) >= 3)
        estado = fuente.estado()
        assert not estado.conectada
        assert estado.aviso is not None
        assert "Sin conexión con Hyperliquid" in estado.aviso
        await conexion.parar()

    correr(prueba())

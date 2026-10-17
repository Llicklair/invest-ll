"""Apoyo de los tests en vivo: mensajes reales de Hyperliquid y un reloj que se mueve a mano.

Los mensajes de `tests/fixtures/hyperliquid/` se capturaron del servicio el 17-oct-2026 (y se
recortaron a unas pocas monedas y niveles). La vela en curso de los mensajes es la de las 17:04 UTC
de ese día; `Reloj` empieza a las 17:04:30 para que siga abierta.
"""

from __future__ import annotations

import asyncio
import json
import socket
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from invest_ll.vivo.hyperliquid import FuenteHyperliquid

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Generator

CARPETA = Path(__file__).resolve().parent / "hyperliquid"
_SOCKET_REAL = socket.socket
"""Se captura al importar, antes de que la suite ponga el bloqueo de red."""


@contextmanager
def bucle() -> Generator[asyncio.Runner]:
    """Un bucle de asyncio para probar corrutinas con la red bloqueada.

    Todo bucle abre al crearse un par de sockets locales para despertarse (ver
    tests/integration/conftest.py): se crea con el socket real puesto solo ese momento.
    """
    bloqueado = socket.socket
    socket.socket = _SOCKET_REAL  # type: ignore[misc]
    try:
        runner = asyncio.Runner(loop_factory=asyncio.SelectorEventLoop)
        runner.get_loop()
    finally:
        socket.socket = bloqueado  # type: ignore[misc]
    try:
        yield runner
    finally:
        runner.close()


def mensaje(nombre: str) -> Any:
    return json.loads((CARPETA / nombre).read_text(encoding="utf-8"))


class Reloj:
    """Hora de pared y reloj monótono que avanzan solo cuando se les dice."""

    def __init__(self) -> None:
        self.hora = datetime(2026, 10, 17, 17, 4, 30, tzinfo=UTC)
        self.mono = 1000.0

    def ahora(self) -> datetime:
        return self.hora

    def monotono(self) -> float:
        return self.mono

    def pasar(self, segundos: float) -> None:
        self.hora += timedelta(seconds=segundos)
        self.mono += segundos


def fuente_con_datos(reloj: Reloj) -> FuenteHyperliquid:
    """Una fuente como la de un panel conectado que sigue el libro y las velas de 1m de BTC."""
    fuente = FuenteHyperliquid(reloj=reloj.ahora, monotono=reloj.monotono)
    fuente.abierta()
    fuente.recibir_meta(mensaje("rest_metaAndAssetCtxs.json"))
    fuente.recibir(mensaje("ws_allMids.json"))
    fuente.seguir("BTC", libro=True, intervalos=["1m"])
    fuente.por_rellenar()
    fuente.recibir_velas(
        "BTC", "1m", mensaje("rest_candleSnapshot_1m.json"), pedidas_en=fuente.marca()
    )
    fuente.recibir(mensaje("ws_l2Book.json"))
    for nombre in ("ws_candle.json", "ws_trades.json"):
        lista: list[dict[str, Any]] = mensaje(nombre)
        for m in lista:
            fuente.recibir(m)
    return fuente

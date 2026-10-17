"""Lo que comparten los tests de la API del panel (`test_api_*.py`).

Cada test corre en su propio directorio temporal: las rutas de datos de la API son relativas al
directorio de trabajo (`data/market`, `portfolio`, `ledger`...), igual que las de la línea de
comandos, así que `monkeypatch.chdir` basta para que ninguno toque los datos del proyecto.

**El TestClient y el bloqueo de red.** La suite corta la red sustituyendo `socket.socket` por una
función que falla (`tests/conftest.py`). El TestClient de FastAPI no abre conexiones, pero sí
arranca un bucle de asyncio en otro hilo, y en Windows eso choca de dos formas con el bloqueo:

1. Todo bucle crea al arrancar un par de sockets conectados entre sí en la propia máquina (su
   "self-pipe", para despertarse desde otros hilos). Con el bloqueo puesto, `RedProhibidaError`.
2. El bucle por defecto de Windows (Proactor) comprueba `isinstance(x, socket.socket)` cada vez
   que vuelve a escuchar ese par; con `socket.socket` convertido en función, esa comprobación
   revienta dentro del bucle y la primera petición se queda esperando para siempre.

Por eso el cliente se arranca con un bucle de selectores (que no hace esa comprobación) y con el
socket real restaurado **solo mientras arranca**. Durante las peticiones el bloqueo vuelve a estar
puesto: una ruta que intentara salir a la red seguiría fallando, que es lo que importa.
"""

from __future__ import annotations

import asyncio
import socket
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from invest_ll.api.app import crear_app
from invest_ll.live.mode import (
    VAR_CLAVE_PRUEBAS,
    VAR_CLAVE_REAL,
    VAR_MODO,
    VAR_SECRETO_PRUEBAS,
    VAR_SECRETO_REAL,
    VAR_TESTNET_HECHA,
)

from .api_apoyo import Api

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterator
    from pathlib import Path

# Se captura al importar, antes de que el fixture de la suite ponga el bloqueo.
_SOCKET_REAL = socket.socket


@pytest.fixture
def cliente(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Api]:
    """La API completa, sin frontend, en un directorio vacío y en modo simulación."""
    monkeypatch.chdir(tmp_path)
    for variable in (
        VAR_MODO,
        VAR_CLAVE_PRUEBAS,
        VAR_SECRETO_PRUEBAS,
        VAR_CLAVE_REAL,
        VAR_SECRETO_REAL,
        VAR_TESTNET_HECHA,
    ):
        monkeypatch.delenv(variable, raising=False)

    bloqueado = socket.socket
    socket.socket = _SOCKET_REAL  # type: ignore[misc]
    try:
        api = TestClient(
            crear_app(frontend=None),
            backend_options={"loop_factory": asyncio.SelectorEventLoop},
        )
        api.__enter__()
    finally:
        socket.socket = bloqueado  # type: ignore[misc]
    try:
        yield Api(api)
    finally:
        api.__exit__(None, None, None)

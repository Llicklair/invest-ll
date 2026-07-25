"""Configuración global de la suite (T004).

**La red está cortada durante todos los tests** (FR-024, SC-002).

Un test que depende de la red no es un test: es una consulta al estado del mundo. Falla cuando no
hay conexión, cuando el proveedor cambia el formato y cuando el activo deja de existir — y cuando
falla, no dice nada sobre si el código está bien.

Cortarla aquí convierte esa regla en algo mecánico. Si alguien escribe un test que llama de verdad
a un proveedor, no pasará por descuido: fallará con un mensaje que explica por qué.
"""

# pyright: reportUnknownMemberType=false

from __future__ import annotations

import socket
from collections.abc import Iterator
from typing import Any, NoReturn

import pytest

_SOCKET_REAL = socket.socket


class RedProhibidaError(RuntimeError):
    """Un test intentó abrir una conexión."""


def _sin_red(*args: Any, **kwargs: Any) -> NoReturn:
    raise RedProhibidaError(
        "Este test intentó abrir una conexión de red. La suite corre sin red a propósito "
        "(FR-024): usa RecordedProvider con respuestas grabadas. Si de verdad necesitas red, "
        "marca el test con @pytest.mark.network y ejecútalo aparte."
    )


@pytest.fixture(autouse=True)
def bloquear_red(request: pytest.FixtureRequest) -> Iterator[None]:
    """Corta el acceso a red salvo en los tests marcados con `network`."""
    if request.node.get_closest_marker("network"):
        yield
        return

    socket.socket = _sin_red  # type: ignore[assignment]
    try:
        yield
    finally:
        socket.socket = _SOCKET_REAL  # type: ignore[assignment]

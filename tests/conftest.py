"""Configuración global de la suite (T004).

**La red está cortada durante todos los tests** (FR-024, SC-002).

Un test que depende de la red no es un test: es una consulta al estado del mundo. Falla cuando no
hay conexión, cuando el proveedor cambia el formato y cuando el activo deja de existir — y cuando
falla, no dice nada sobre si el código está bien.

Cortarla aquí convierte esa regla en algo mecánico. Si alguien escribe un test que llama de verdad
a un proveedor, no pasará por descuido: fallará con un mensaje que explica por qué.

**La reserva de datos del proyecto también se ignora**, por la misma razón: es estado del mundo,
no del código. Ver `reserva_aislada`.
"""

# pyright: reportUnknownMemberType=false

from __future__ import annotations

import socket
from collections.abc import Iterator
from typing import Any, NoReturn

import keyring
import pytest

from .almacen_en_memoria import AlmacenEnMemoria

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


@pytest.fixture(autouse=True)
def almacen_de_claves() -> Iterator[AlmacenEnMemoria]:
    """**Ningún test toca el almacén de credenciales del sistema.**

    El panel guarda las claves de Binance con `keyring` (en Windows, el Administrador de
    credenciales). Sin esto, cualquier test que pasara por el modo efectivo leería —y los de la
    conexión escribirían— las credenciales reales de quien corre la suite. Se pone en todos los
    tests y se quita al acabar; quien quiera mirar lo guardado pide este fixture.
    """
    anterior = keyring.get_keyring()
    almacen = AlmacenEnMemoria()
    keyring.set_keyring(almacen)
    try:
        yield almacen
    finally:
        keyring.set_keyring(anterior)


@pytest.fixture(autouse=True)
def reserva_aislada(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ignora la reserva de datos declarada en el proyecto.

    `data/market/reserved.json` es una decisión de investigación de quien usa el proyecto, no una
    propiedad del código. Sin este aislamiento, fijar una reserva —algo que el sistema invita a
    hacer— ponía en rojo tests que cargan series con fechas recientes: fallaban por un fichero que
    ellos no habían escrito, y el mensaje hablaba de datos reservados en mitad de un test sobre el
    almacén. Un test que depende del estado del repositorio no dice nada sobre si el código
    está bien.

    Los tests que sí comprueban el recorte vuelven a sustituir este mismo nombre por una reserva
    propia en un directorio temporal; su fixture se aplica después que este y gana.
    """
    monkeypatch.setattr("invest_ll.data.loader.load_reservation", lambda: None)

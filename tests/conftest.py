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
from pathlib import Path
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
def conectores_de_exchanges_limpios() -> Iterator[None]:
    """**Ningún conector falso ni guardado pasa de un test a otro** (`exchanges.registro`).

    El registro guarda los conectores que construye (cargar los mercados cuesta) y los falsos que
    inyecta un test (`registro.inyectar`). Sin esto, un falso de un test respondería en el
    siguiente.
    """
    from invest_ll.exchanges import registro

    registro.quitar_inyectados()
    try:
        yield
    finally:
        registro.quitar_inyectados()


RAIZ_REPO = Path(__file__).resolve().parents[1]
NO_SE_VIGILA = frozenset(
    {
        # Cachés de las herramientas, que viven ahí a propósito.
        ".pytest_cache",
        ".hypothesis",
        ".ruff_cache",
        "__pycache__",
        ".coverage",
        # El entorno, el control de versiones y el código: al importarlo se escriben sus
        # `__pycache__`, que cambian la fecha de sus carpetas sin ser basura de ningún test.
        ".venv",
        ".git",
        "src",
        "tests",
    }
)


def foto_de_la_raiz(raiz: Path = RAIZ_REPO, *, con_su_contenido: bool = False) -> dict[str, int]:
    """Lo que hay en la raíz del repositorio y cuándo cambió cada cosa (salvo `NO_SE_VIGILA`).

    La fecha de una carpeta cambia al crear o borrar algo dentro: así se ve también un test que
    crea un fichero en una carpeta que ya existía (`attempts/` de una pasada anterior). Con
    `con_su_contenido`, además, lo que hay dentro de cada carpeta de la raíz, que ve también un
    fichero sobrescrito sin crear nada. Se pide con un `stat` de cada entrada y no con la fecha del
    listado: en Windows, el listado guarda una copia que NTFS actualiza tarde.
    """
    foto: dict[str, int] = {}
    for ruta in raiz.iterdir():
        if ruta.name in NO_SE_VIGILA:
            continue
        foto[ruta.name] = ruta.stat().st_mtime_ns
        if con_su_contenido and ruta.is_dir():
            for dentro in ruta.iterdir():
                foto[f"{ruta.name}/{dentro.name}"] = dentro.stat().st_mtime_ns
    return foto


def _tocado(antes: dict[str, int], despues: dict[str, int]) -> list[str]:
    return sorted(n for n in despues.keys() | antes.keys() if despues.get(n) != antes.get(n))


ESCRIBIR_EN_TMP = (
    "cámbiate antes a un directorio temporal (monkeypatch.chdir(tmp_path)) o pásale rutas de "
    "tmp_path"
)


@pytest.fixture(autouse=True)
def raiz_sin_basura() -> Iterator[None]:
    """**Ningún test escribe en la raíz del repositorio.**

    Las rutas de datos del proyecto (`attempts/`, `portfolio/`, `ledger/`, `plan/`...) son relativas
    al directorio de trabajo, que al correr la suite es la raíz. Un test que se olvida de cambiarse
    a un directorio temporal deja ahí sus datos de prueba (pasó: `attempts/attempts.json` con AAA y
    BBB) o, peor, escribe sobre los de quien corre la suite. Este falla en el test que lo hizo; lo
    que se le escape (sobrescribir un fichero que ya estaba), lo ve `raiz_sin_basura_al_final`.
    """
    antes = foto_de_la_raiz()
    yield
    tocado = _tocado(antes, foto_de_la_raiz())
    assert not tocado, f"este test ha escrito en la raíz ({', '.join(tocado)}): {ESCRIBIR_EN_TMP}"


@pytest.fixture(autouse=True, scope="session")
def raiz_sin_basura_al_final() -> Iterator[None]:
    """Lo mismo, un nivel más hondo y una sola vez para toda la suite (mirar dentro de cada
    carpeta en cada test costaría segundos)."""
    antes = foto_de_la_raiz(con_su_contenido=True)
    yield
    tocado = _tocado(antes, foto_de_la_raiz(con_su_contenido=True))
    assert not tocado, f"la suite ha escrito en la raíz ({', '.join(tocado)}): {ESCRIBIR_EN_TMP}"


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

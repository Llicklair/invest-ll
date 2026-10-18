"""El motor de bots como servicio aparte: siempre encendido, aunque cierres el panel.

Hasta ahora el motor vivía dentro del panel: cerrar su ventana, reiniciarlo para traer código
nuevo o un fallo del panel paraban los bots. Ahora es **su propio proceso**, oculto (`pythonw`),
con su propia conexión a Hyperliquid, que escucha en 127.0.0.1:8602:

- sirve la API de los bots (`/api/bots…`, `/api/actividad…`, las mismas rutas de siempre) y
  `/api/motor/salud`; el panel (8601) le pasa esas peticiones tal cual (`ProxyMotor`) y el stream
  le pregunta por HTTP (`bots_remotos`, `actividad_remota`);
- lo arranca el panel al abrirse si no está en marcha, `invest-ll-motor arrancar`, o Windows al
  iniciar sesión (opcional: un `.vbs` en la carpeta Inicio, `instalar_inicio`);
- nace **desligado** del panel: un lanzador intermedio (`lanzar`) lo arranca y se va, así que
  levantar.cmd, que mata el árbol de procesos del panel para reiniciarlo, no se lo lleva por
  delante; y sale del "job" de Windows del padre si lo hay;
- uno solo: si el puerto ya está ocupado, otro motor está en marcha y este no arranca;
- deja su rastro en `bots/motor.log` y su ficha (pid, desde cuándo, versión del código) en
  `bots/.motor.json`; con la opción `mantener_despierto`, mientras haya bots en marcha, Windows no
  se duerme solo.

Lo que sale a la red (escuchar en 8602, preguntar al motor) está aquí: la suite lo sustituye
(`tests/unit/test_no_network_in_suite.py` lo tiene en su lista).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import logging.handlers
import os
import socket
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

import httpx

from invest_ll.bots.registro import CARPETA

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import AsyncGenerator, Sequence

    from fastapi import FastAPI
    from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger(__name__)

HOST: Final = "127.0.0.1"
PUERTO: Final = 8602
URL: Final = f"http://{HOST}:{PUERTO}"
FICHA: Final = ".motor.json"
CERROJO: Final = ".motor.lock"
"""Un cerrojo del sistema: mientras un motor lo tiene, ningún otro arranca (ni un instante)."""
ENTRE_ARRANQUES: Final = 30.0
"""Desde el panel, como mucho un intento de arrancarlo cada tantos segundos."""
REGISTRO: Final = "motor.log"
OPCIONES: Final = Path("config") / "motor.json"
NOMBRE_INICIO: Final = "INVEST LL - motor de bots.vbs"
PLAZO_SALUD: Final = 1.5
PLAZO_LARGO: Final = 180.0
"""Lo que se espera al motor en lo que descarga velas (el examen de un bot sobre el pasado)."""
CADA_DESPIERTO: Final = 60.0
RUTAS_DEL_MOTOR: Final = ("/api/bots", "/api/bots-real", "/api/actividad")
"""Lo que el panel pasa al motor (y todo lo que cuelga de ahí)."""

# Banderas de CreateProcess (Windows).
DETACHED_PROCESS: Final = 0x00000008
CREATE_NEW_PROCESS_GROUP: Final = 0x00000200
CREATE_NO_WINDOW: Final = 0x08000000
CREATE_BREAKAWAY_FROM_JOB: Final = 0x01000000
# SetThreadExecutionState.
ES_CONTINUOUS: Final = 0x80000000
ES_SYSTEM_REQUIRED: Final = 0x00000001

_remoto = False
"""En el panel: los bots viven en el servicio (el panel no tiene motor propio)."""
_servidor: Any = None
"""El uvicorn del servicio, para poder apagarlo desde su propia API."""
_ultimo_arranque = float("-inf")


# -- Dónde está todo -------------------------------------------------------------------------------


def raiz_del_proyecto() -> Path:
    """La carpeta del proyecto (la del pyproject.toml de invest-ll), subiendo desde este paquete:
    Windows arranca el servicio desde cualquier carpeta."""
    for carpeta in Path(__file__).resolve().parents:
        pyproject = carpeta / "pyproject.toml"
        with contextlib.suppress(OSError):
            if pyproject.is_file() and 'name = "invest-ll"' in pyproject.read_text(
                encoding="utf-8"
            ):
                return carpeta
    return Path.cwd()


def version_del_codigo() -> float:
    """La última vez que cambió el código del paquete (la fecha del .py más reciente): si el motor
    arrancó antes, lleva código viejo."""
    paquete = Path(__file__).resolve().parents[1]
    return max((p.stat().st_mtime for p in paquete.rglob("*.py")), default=0.0)


def pythonw() -> str:
    """El Python sin ventana del mismo entorno (en Windows); fuera de Windows, el de siempre."""
    exe = Path(sys.executable)
    sin_ventana = exe.with_name("pythonw.exe")
    return str(sin_ventana if sys.platform == "win32" and sin_ventana.is_file() else exe)


# -- Opciones (config/motor.json, fuera de git) ----------------------------------------------------


@dataclass(frozen=True, slots=True)
class Opciones:
    mantener_despierto: bool = False


def leer_opciones(raiz: Path | None = None) -> Opciones:
    ruta = (raiz or Path.cwd()) / OPCIONES
    try:
        datos: object = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Opciones()
    d = cast("dict[str, object]", datos) if isinstance(datos, dict) else {}
    return Opciones(mantener_despierto=bool(d.get("mantener_despierto", False)))


def guardar_opciones(o: Opciones, raiz: Path | None = None) -> None:
    ruta = (raiz or Path.cwd()) / OPCIONES
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps({"mantener_despierto": o.mantener_despierto}), encoding="utf-8")


# -- El servicio -----------------------------------------------------------------------------------


def _escribir_ficha() -> None:
    ficha = {
        "pid": os.getpid(),
        "puerto": PUERTO,
        "desde": datetime.now(UTC).isoformat(),
        "version": version_del_codigo(),
    }
    (CARPETA / FICHA).write_text(json.dumps(ficha), encoding="utf-8")


def _despierto(motor_activo: Any) -> None:
    """Mientras haya bots en marcha y la opción esté puesta, Windows no se duerme solo (la
    pantalla sí se apaga). Si no, se le deja dormir."""
    if sys.platform != "win32":  # pragma: no cover
        return
    hay = motor_activo is not None and any(
        b.estado.estado == "en_marcha" for b in motor_activo.bots()
    )
    estado = ES_CONTINUOUS | (
        ES_SYSTEM_REQUIRED if hay and leer_opciones().mantener_despierto else 0
    )
    ctypes_kernel32().SetThreadExecutionState(estado)


def _copia_si_toca(motor_activo: Any) -> None:
    """Una copia de seguridad al día de lo que no está en git (`invest_ll.copias`), con el motor
    quieto mientras se lee `bots/` para que la copia sea de un momento."""
    from invest_ll import copias

    if not copias.toca():
        return
    cerrojo = motor_activo.cerrojo if motor_activo is not None else contextlib.nullcontext()
    with cerrojo:
        hecha = copias.hacer(raiz_del_proyecto())
    log.info("copia de seguridad hecha: %s", hecha.ruta)


def ctypes_kernel32() -> Any:  # pragma: no cover - solo en Windows
    import ctypes

    return ctypes.windll.kernel32  # type: ignore[attr-defined]


@asynccontextmanager
async def _vida(_: FastAPI) -> AsyncGenerator[None]:
    """La conexión con Hyperliquid y el motor viven lo que vive el servicio."""
    from invest_ll.bots import motor
    from invest_ll.vivo import servicio as vivo

    await vivo.arrancar()
    await motor.arrancar()
    _escribir_ficha()

    async def vigilar_despierto() -> None:
        while True:
            with contextlib.suppress(Exception):
                _despierto(motor.activo())
            try:
                await asyncio.to_thread(_copia_si_toca, motor.activo())
            except Exception:
                log.exception("no se pudo hacer la copia de seguridad")
            await asyncio.sleep(CADA_DESPIERTO)

    tarea = asyncio.get_running_loop().create_task(vigilar_despierto())
    log.info("motor de bots en marcha en %s (pid %s)", URL, os.getpid())
    try:
        yield
    finally:
        tarea.cancel()
        with contextlib.suppress(Exception):
            if sys.platform == "win32":
                ctypes_kernel32().SetThreadExecutionState(ES_CONTINUOUS)
        await motor.parar()
        await vivo.parar()
        with contextlib.suppress(OSError):
            (CARPETA / FICHA).unlink()
        log.info("motor de bots parado")


def crear_app_motor(*, con_vida: bool = True) -> FastAPI:
    """La app del servicio: la API de los bots, su salud y apagarlo. `con_vida=False` (los tests):
    sin conectar con Hyperliquid ni arrancar el bucle."""
    from fastapi import APIRouter, FastAPI

    from invest_ll.api import bots as rutas_bots
    from invest_ll.api.app import blindar, instalar_errores
    from invest_ll.api.errores import RESPUESTAS_DE_ERROR

    app = FastAPI(
        lifespan=_vida if con_vida else None,
        title="INVEST LL · motor de bots",
        description="El servicio de los bots: el panel le pasa sus rutas. Solo 127.0.0.1.",
    )
    # Solo le habla el panel (su proxy) y la terminal: ninguna web, ni la de desarrollo.
    blindar(app)
    instalar_errores(app)
    router = APIRouter(prefix="/api", responses=RESPUESTAS_DE_ERROR)
    router.include_router(rutas_bots.router)

    @router.get("/motor/salud", tags=["motor"])
    def salud() -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        from invest_ll.bots import motor

        m = motor.activo()
        bots = m.bots() if m is not None else []
        ficha: dict[str, Any] = {}
        with contextlib.suppress(OSError, ValueError):
            leida: object = json.loads((CARPETA / FICHA).read_text(encoding="utf-8"))
            ficha = cast("dict[str, Any]", leida) if isinstance(leida, dict) else {}
        return {
            "pid": os.getpid(),
            "desde": ficha.get("desde"),
            "version": ficha.get("version", 0.0),
            "bots": len(bots),
            "en_marcha": sum(1 for b in bots if b.estado.estado == "en_marcha"),
        }

    @router.post("/motor/apagar", tags=["motor"], status_code=202)
    def apagar() -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        """Para el servicio con calma (guarda el estado de cada bot)."""
        if _servidor is not None:
            _servidor.should_exit = True
        return {"apagando": True}

    app.include_router(router)
    return app


def tomar_cerrojo(carpeta: Path = CARPETA) -> Any | None:
    """El cerrojo de motor único: el fichero abierto (hay que guardarlo mientras dure el proceso:
    al cerrarse o al morir el proceso, el sistema lo suelta), o None si otro motor lo tiene."""
    carpeta.mkdir(exist_ok=True)
    fichero = (carpeta / CERROJO).open("a+b")
    try:
        if sys.platform == "win32":
            import msvcrt

            fichero.seek(0)
            msvcrt.locking(fichero.fileno(), msvcrt.LK_NBLCK, 1)
        else:  # pragma: no cover
            import fcntl

            fcntl.flock(fichero, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fichero.close()
        return None
    return fichero


def correr() -> int:
    """El servicio en primer plano (lo que corre oculto). 0 si ya había otro en marcha.

    Antes de cargar ningún bot: el cerrojo de motor único y el puerto. Dos motores a la vez sobre
    los mismos bots operarían dos veces; si arrancan a la vez (el panel y Windows, o varias
    peticiones), solo uno pasa de aquí."""
    import uvicorn

    raiz = raiz_del_proyecto()
    os.chdir(raiz)
    CARPETA.mkdir(exist_ok=True)
    manejador = logging.handlers.RotatingFileHandler(
        CARPETA / REGISTRO, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[manejador], force=True)
    cerrojo = tomar_cerrojo()
    if cerrojo is None:
        log.info("ya hay un motor de bots en marcha (tiene el cerrojo): este no arranca")
        return 0
    escucha = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        escucha.bind((HOST, PUERTO))
    except OSError as error:
        escucha.close()
        log.error("el puerto %s está ocupado (%s): el motor no arranca", PUERTO, error)
        return 1
    global _servidor
    _servidor = uvicorn.Server(
        uvicorn.Config(
            crear_app_motor(),
            host=HOST,
            port=PUERTO,
            log_config=None,
            access_log=False,
            timeout_graceful_shutdown=3,
        )
    )
    try:
        _servidor.run(sockets=[escucha])
    finally:
        cerrojo.close()
    return 0


# -- Lanzarlo desligado del panel ------------------------------------------------------------------


def _popen_desligado(orden: list[str], cwd: Path) -> None:
    """Un proceso sin ventana, en su propio grupo y fuera del job del padre si se puede."""
    if sys.platform != "win32":  # pragma: no cover
        subprocess.Popen(orden, cwd=cwd, start_new_session=True, close_fds=True)
        return
    base = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    nada = subprocess.DEVNULL
    try:
        subprocess.Popen(
            orden,
            cwd=cwd,
            creationflags=base | CREATE_BREAKAWAY_FROM_JOB,
            close_fds=True,
            stdin=nada,
            stdout=nada,
            stderr=nada,
        )
    except OSError:
        # El job del padre no deja salirse: sin esa bandera (el motor dura lo que dure el padre).
        subprocess.Popen(
            orden, cwd=cwd, creationflags=base, close_fds=True, stdin=nada, stdout=nada, stderr=nada
        )


def lanzar() -> int:
    """El lanzador intermedio: arranca el servicio y se va, para que el servicio no quede colgando
    del panel (levantar.cmd mata el árbol del panel al reiniciarlo)."""
    raiz = raiz_del_proyecto()
    _popen_desligado([pythonw(), "-m", "invest_ll.bots.servicio", "correr"], raiz)
    return 0


def arrancar_en_segundo_plano() -> None:
    """Arranca el servicio (a través del lanzador) sin esperar."""
    raiz = raiz_del_proyecto()
    _popen_desligado([pythonw(), "-m", "invest_ll.bots.servicio", "lanzar"], raiz)


def arrancar_si_hace_falta() -> bool:
    """Desde el panel: lo arranca si no contesta y no se ha intentado hace poco (muchas peticiones
    a la vez no lanzan muchos motores; el cerrojo, además, deja pasar a uno solo). Si lo lanzó."""
    global _ultimo_arranque
    ahora = time.monotonic()
    if ahora - _ultimo_arranque < ENTRE_ARRANQUES or en_marcha() is not None:
        return False
    _ultimo_arranque = ahora
    arrancar_en_segundo_plano()
    return True


def esperar_en_marcha(segundos: float = 20.0) -> dict[str, Any] | None:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        salud = en_marcha()
        if salud is not None:
            return salud
        time.sleep(0.5)
    return None


# -- Preguntarle (el panel) ------------------------------------------------------------------------


def en_marcha() -> dict[str, Any] | None:
    """La salud del servicio, o None si no contesta."""
    try:
        r = httpx.get(f"{URL}/api/motor/salud", timeout=PLAZO_SALUD)
        if r.status_code != 200:
            return None
        datos: object = r.json()
    except (httpx.HTTPError, ValueError):
        return None
    return cast("dict[str, Any]", datos) if isinstance(datos, dict) else None


def apagar() -> bool:
    """Le pide que se pare con calma. False si no contestaba."""
    try:
        httpx.post(f"{URL}/api/motor/apagar", timeout=PLAZO_SALUD)
    except httpx.HTTPError:
        return False
    return True


def usar_remoto(si: bool) -> None:
    """El panel lo pone al arrancar: sus bots viven en el servicio."""
    global _remoto
    _remoto = si


def remoto() -> bool:
    return _remoto


def bots_remotos() -> dict[str, Any] | None:
    """`GET /api/bots` del servicio (para el canal `bots` del stream del panel)."""
    try:
        r = httpx.get(f"{URL}/api/bots", timeout=5.0)
        datos: object = r.json() if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None
    return cast("dict[str, Any]", datos) if isinstance(datos, dict) else None


def actividad_remota(vista: int | None) -> dict[str, Any] | None:
    """Lo nuevo del feed en el servicio (para el canal `actividad` del stream del panel)."""
    params = {} if vista is None else {"vista": vista}
    try:
        r = httpx.get(f"{URL}/api/actividad/nueva", params=params, timeout=5.0)
        datos: object = r.json() if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None
    return cast("dict[str, Any]", datos) if isinstance(datos, dict) else None


def cliente_proxy() -> httpx.AsyncClient:
    """El cliente con que el panel pasa peticiones al servicio (los tests lo sustituyen)."""
    return httpx.AsyncClient(base_url=URL, timeout=30.0)


class ProxyMotor:
    """En el panel: las rutas de los bots se pasan tal cual al servicio. Si no contesta, 503 en
    llano (y se intenta arrancar)."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        ruta = str(scope.get("path", ""))
        es_del_motor = scope["type"] == "http" and any(
            ruta == r or ruta.startswith(r + "/") for r in RUTAS_DEL_MOTOR
        )
        if not (_remoto and es_del_motor):
            await self._app(scope, receive, send)
            return
        from starlette.requests import Request
        from starlette.responses import JSONResponse, Response

        peticion = Request(scope, receive)
        cuerpo = await peticion.body()
        cabeceras = {
            k: v for k, v in peticion.headers.items() if k.lower() in ("content-type", "accept")
        }
        try:
            async with cliente_proxy() as cliente:
                r = await cliente.request(
                    peticion.method,
                    ruta,
                    params=list(peticion.query_params.multi_items()),
                    content=cuerpo,
                    headers=cabeceras,
                    timeout=PLAZO_LARGO if ruta.endswith("/examen") else httpx.USE_CLIENT_DEFAULT,
                )
        except httpx.TimeoutException:
            respuesta: Response = JSONResponse(
                status_code=504,
                content={
                    "detail": "El motor de los bots tardó demasiado en contestar (sigue en marcha). "
                    "Vuelve a intentarlo en un momento."
                },
            )
        except httpx.HTTPError:
            await asyncio.to_thread(arrancar_si_hace_falta)
            respuesta = JSONResponse(
                status_code=503,
                content={
                    "detail": "El motor de los bots no contestaba: se está arrancando. Vuelve a "
                    "intentarlo en unos segundos."
                },
            )
        else:
            respuesta = Response(
                content=r.content,
                status_code=r.status_code,
                media_type=r.headers.get("content-type"),
            )
        await respuesta(scope, receive, send)


# -- Arrancar con Windows (carpeta Inicio) ---------------------------------------------------------


def carpeta_inicio() -> Path:
    appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def inicio_instalado() -> bool:
    return (carpeta_inicio() / NOMBRE_INICIO).is_file()


def instalar_inicio() -> Path:
    """Un .vbs en la carpeta Inicio de Windows que arranca el servicio oculto al iniciar sesión."""
    raiz = raiz_del_proyecto()
    ruta = carpeta_inicio() / NOMBRE_INICIO
    ruta.parent.mkdir(parents=True, exist_ok=True)
    texto = (
        "' INVEST LL: arranca el motor de los bots, oculto, al iniciar sesion.\n"
        "' Se quita desde el panel (Bots > Motor de los bots) o borrando este fichero.\n"
        'Set s = CreateObject("WScript.Shell")\n'
        f's.CurrentDirectory = "{raiz}"\n'
        f's.Run """{pythonw()}"" -m invest_ll.bots.servicio lanzar", 0, False\n'
    )
    # Fin de línea de Windows (VBScript), sin duplicarlo.
    ruta.write_text(texto, encoding="utf-8", newline="\r\n")
    return ruta


def quitar_inicio() -> bool:
    ruta = carpeta_inicio() / NOMBRE_INICIO
    if not ruta.is_file():
        return False
    ruta.unlink()
    return True


# -- invest-ll-motor -------------------------------------------------------------------------------


def _datos_de(salud: dict[str, Any] | None) -> dict[str, object]:
    """Lo que dice `--json` del motor."""
    if salud is None:
        return {"en_marcha": False}
    return {
        "en_marcha": True,
        "pid": salud.get("pid"),
        "desde": salud.get("desde"),
        "bots": salud.get("bots"),
        "bots_en_marcha": salud.get("en_marcha"),
    }


def main(argv: Sequence[str] | None = None) -> int:
    from invest_ll.cli.emit import add_json_flag, salida_de

    parser = argparse.ArgumentParser(
        prog="invest-ll-motor",
        description="El motor de los bots de INVEST LL, aparte del panel (127.0.0.1:8602).",
    )
    parser.add_argument(
        "orden",
        nargs="?",
        default="estado",
        choices=["estado", "arrancar", "parar", "reiniciar", "correr", "lanzar"],
        help="estado (por defecto), arrancar, parar, reiniciar; correr/lanzar son de uso interno",
    )
    add_json_flag(parser)
    args = parser.parse_args(argv)
    if args.orden == "correr":
        return correr()
    if args.orden == "lanzar":
        return lanzar()
    salida = salida_de(args, "motor")
    if args.orden in ("parar", "reiniciar"):
        estaba = apagar()
        if estaba:
            for _ in range(40):
                if en_marcha() is None:
                    break
                time.sleep(0.25)
        salida.dato(parado=estaba)
        salida.linea(
            "Motor de los bots parado." if estaba else "El motor de los bots no estaba en marcha."
        )
        if args.orden == "parar":
            return salida.cerrar(0)
    if args.orden in ("arrancar", "reiniciar"):
        if en_marcha() is None:
            arrancar_en_segundo_plano()
        salud = esperar_en_marcha()
        if salud is None:
            return salida.error("El motor no arrancó: mira bots/motor.log.", 1)
        salida.dato(**_datos_de(salud))
        salida.linea("Motor de los bots en marcha.")
        return salida.cerrar(0)
    salud = en_marcha()
    salida.dato(**_datos_de(salud))
    if salud is None:
        salida.linea("El motor de los bots está parado. Arráncalo con: invest-ll-motor arrancar")
        return salida.cerrar(1)
    salida.linea(
        f"Motor de los bots en marcha (pid {salud.get('pid')}, desde {salud.get('desde')}): "
        f"{salud.get('en_marcha')} de {salud.get('bots')} bots en marcha."
    )
    return salida.cerrar(0)


if __name__ == "__main__":
    raise SystemExit(main())

"""La aplicación FastAPI del panel: la API en `/api` y el frontend ya compilado en `/`.

Un solo proceso y un solo puerto (8601), como antes: el frontend de Next.js se exporta como
ficheros estáticos (`web/out`) y los sirve esta misma aplicación. Arrancar el panel sigue siendo
arrancar UNA cosa. En desarrollo, `npm run dev` en `web/` (puerto 3000) habla con esta API, y por
eso se permite ese origen y ninguno más.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Final

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException as StarletteHTTPException

from invest_ll.api.errores import EN_LLANO, explicar_validacion
from invest_ll.api.rutas import router
from invest_ll.bots.servicio import ProxyMotor
from invest_ll.errors import InvestLLError

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import AsyncGenerator, Sequence

    from starlette.types import ASGIApp, Message, Receive, Scope, Send

RAIZ_REPO = Path(__file__).resolve().parents[3]
FRONTEND = RAIZ_REPO / "web" / "out"
ORIGENES_DESARROLLO = ("http://localhost:3000", "http://127.0.0.1:3000")
# Solo se atienden peticiones dirigidas a esta maquina por su nombre local ("testserver" es el
# del TestClient). Escuchar en 127.0.0.1 no basta: con DNS rebinding, una web cualquiera abierta
# en el navegador puede hacer que su dominio resuelva a 127.0.0.1 y hablar con el panel como si
# fuera el mismo origen -- y POST /api/ordenes, en modo real, mueve dinero. Comprobar la cabecera
# Host corta ese camino: el navegador manda el dominio del atacante, no "localhost".
HOSTS_PERMITIDOS = ("127.0.0.1", "localhost", "testserver")
HOST_AJENO: Final = (
    "El panel solo atiende a este mismo equipo (localhost): esta petición venía dirigida a otro "
    "nombre y no se ha atendido."
)
FALLO_INTERNO: Final = (
    "Algo ha fallado dentro del panel ({tipo}). No es por tus datos: vuelve a intentarlo y, si se "
    "repite, la terminal donde arrancaste el panel dice qué fue."
)


class SoloEsteEquipo:
    """Rechaza (400) lo que no venga dirigido a este equipo por su nombre local.

    Hace lo mismo que el `TrustedHostMiddleware` de Starlette con una lista sin comodines (mira el
    nombre de la cabecera Host, sin el puerto), pero responde con la forma de todos los errores del
    panel, `{"detail": ...}`, en vez de un texto en inglés.
    """

    def __init__(self, app: ASGIApp, permitidos: Sequence[str]) -> None:
        self._app = app
        self._permitidos = frozenset(permitidos)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            host = Headers(scope=scope).get("host", "").split(":")[0]
            if host not in self._permitidos:
                await JSONResponse(status_code=400, content={"detail": HOST_AJENO})(
                    scope, receive, send
                )
                return
        await self._app(scope, receive, send)


OTRA_WEB: Final = (
    "El panel solo acepta cambios hechos desde el propio panel: esta petición venía de otra web y "
    "no se ha atendido."
)
METODOS_QUE_CAMBIAN: Final = frozenset({"POST", "PUT", "PATCH", "DELETE"})
SITIO_PROPIO: Final = frozenset({"same-origin", "none"})
"""Los valores de `Sec-Fetch-Site` de una petición del propio panel (o tecleada en la barra)."""


class SoloMismoOrigen:
    """Rechaza (403) lo que cambia algo y lo pide otra web (CSRF).

    Comprobar el Host no basta: una página cualquiera abierta en el navegador puede mandar un POST
    «simple» (sin cuerpo, sin preflight de CORS) a `http://localhost:8601/...`, con el Host bueno, y
    quitar «Parar todo lo real» o reanudar un bot. El navegador dice de dónde viene: con `Origin`
    (que tiene que ser el propio panel o un origen de desarrollo permitido) y con `Sec-Fetch-Site`.
    Lo que no viene de un navegador (la terminal, el proxy del panel al motor, los tests) no trae
    ninguna de las dos y pasa: no hay web ajena detrás.
    """

    def __init__(self, app: ASGIApp, permitidos: Sequence[str] = ()) -> None:
        self._app = app
        self._permitidos = frozenset(permitidos)

    def _ajena(self, scope: Scope) -> bool:
        if scope["type"] != "http" or scope.get("method", "GET") not in METODOS_QUE_CAMBIAN:
            return False
        cabeceras = Headers(scope=scope)
        origen = cabeceras.get("origin")
        if origen is not None:
            propio = f"{scope.get('scheme', 'http')}://{cabeceras.get('host', '')}"
            return origen != propio and origen not in self._permitidos
        sitio = cabeceras.get("sec-fetch-site")
        return sitio is not None and sitio not in SITIO_PROPIO

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self._ajena(scope):
            await JSONResponse(status_code=403, content={"detail": OTRA_WEB})(scope, receive, send)
            return
        await self._app(scope, receive, send)


CABECERAS_SEGURAS: Final = (
    (b"x-content-type-options", b"nosniff"),
    # Que ninguna web meta el panel en un marco (clickjacking sobre «Activar dinero real»).
    (b"x-frame-options", b"DENY"),
    (b"content-security-policy", b"frame-ancestors 'none'"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-opener-policy", b"same-origin"),
    # Que otra web no pueda cargar nada del panel como recurso suyo (<script>, <img>…).
    (b"cross-origin-resource-policy", b"same-origin"),
)


class CabecerasSeguras:
    """Añade a cada respuesta las cabeceras de `CABECERAS_SEGURAS` (si no las trae ya)."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        async def con_cabeceras(mensaje: Message) -> None:
            if mensaje["type"] == "http.response.start":
                lista = list(mensaje.get("headers", []))
                tiene = {nombre.lower() for nombre, _ in lista}
                lista.extend((n, v) for n, v in CABECERAS_SEGURAS if n not in tiene)
                mensaje["headers"] = lista
            await send(mensaje)

        await self._app(scope, receive, con_cabeceras)


def blindar(app: FastAPI, *, origenes: Sequence[str] = ()) -> None:
    """Lo que protege una app que escucha en este equipo (el panel y el motor), por fuera de todo
    lo demás: solo nombres locales (DNS rebinding), solo cambios pedidos desde el propio panel
    (CSRF) y las cabeceras de seguridad en cada respuesta."""
    app.add_middleware(SoloMismoOrigen, permitidos=origenes)
    app.add_middleware(SoloEsteEquipo, permitidos=HOSTS_PERMITIDOS)
    app.add_middleware(CabecerasSeguras)


@asynccontextmanager
async def _en_vivo(_: FastAPI) -> AsyncGenerator[None]:
    """La conexión con Hyperliquid vive lo que vive el panel. Los bots, no: viven en su servicio
    aparte (`bots.servicio`, 127.0.0.1:8602), que sigue aunque se cierre el panel. Si no está en
    marcha, se arranca; las rutas de los bots se le pasan tal cual (`ProxyMotor`)."""
    import asyncio

    from invest_ll.bots import servicio as servicio_bots
    from invest_ll.vivo import servicio

    servicio_bots.usar_remoto(True)
    await asyncio.to_thread(servicio_bots.arrancar_si_hace_falta)
    await servicio.arrancar()
    try:
        yield
    finally:
        await servicio.parar()
        servicio_bots.usar_remoto(False)


def instalar_errores(app: FastAPI) -> None:
    """Todos los errores con la misma forma, `{"detail": "texto en llano"}` (también en el
    servicio de los bots)."""

    @app.exception_handler(InvestLLError)
    async def _dominio(_: Request, error: InvestLLError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.exception_handler(RequestValidationError)
    async def _validacion(_: Request, error: RequestValidationError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return JSONResponse(
            status_code=422, content={"detail": explicar_validacion(error.errors())}
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, error: StarletteHTTPException) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        detalle = error.detail
        return JSONResponse(
            status_code=error.status_code,
            content={"detail": EN_LLANO.get(detalle, detalle)},
            headers=error.headers,
        )

    @app.exception_handler(Exception)
    async def _interno(_: Request, error: Exception) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        # Sigue siendo un 500 (y uvicorn lo deja en la terminal con su traza): un fallo del
        # programa no se disfraza de "dato no válido"; solo cambia la forma de la respuesta.
        return JSONResponse(
            status_code=500, content={"detail": FALLO_INTERNO.format(tipo=type(error).__name__)}
        )


def crear_app(frontend: Path | None = FRONTEND, *, en_vivo: bool = False) -> FastAPI:
    """La aplicación. `en_vivo=True` (solo el lanzador del panel) abre la conexión con Hyperliquid
    y se asegura de que el servicio de los bots esté en marcha; los tests y la generación del
    contrato no tocan la red (y sin `en_vivo` las rutas de los bots se sirven aquí mismo)."""
    app = FastAPI(
        lifespan=_en_vivo if en_vivo else None,
        title="INVEST LL",
        description=(
            "El panel de INVEST LL. Arranca en simulacion; ninguna ruta envia ordenes salvo "
            "POST /api/ordenes, que exige la cantidad tecleada como confirmacion. Todos los "
            'errores tienen la misma forma: {"detail": "texto en llano"}.'
        ),
        version="1.0.0",
    )
    # Lo primero que se añade es lo más interior: el host y el origen se comprueban antes de pasar
    # nada al servicio de los bots.
    app.add_middleware(ProxyMotor)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(ORIGENES_DESARROLLO),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    blindar(app, origenes=ORIGENES_DESARROLLO)
    instalar_errores(app)
    app.include_router(router)

    if frontend is not None and (frontend / "index.html").exists():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app


app = crear_app()

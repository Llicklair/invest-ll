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
from invest_ll.errors import InvestLLError

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import AsyncGenerator, Sequence

    from starlette.types import ASGIApp, Receive, Scope, Send

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


@asynccontextmanager
async def _en_vivo(_: FastAPI) -> AsyncGenerator[None]:
    """La conexión con Hyperliquid y el motor de bots viven lo que vive el panel."""
    from invest_ll.bots import motor
    from invest_ll.vivo import servicio

    await servicio.arrancar()
    await motor.arrancar()
    try:
        yield
    finally:
        await motor.parar()
        await servicio.parar()


def crear_app(frontend: Path | None = FRONTEND, *, en_vivo: bool = False) -> FastAPI:
    """La aplicación. `en_vivo=True` (solo el lanzador del panel) abre la conexión con Hyperliquid
    y arranca los bots; los tests y la generación del contrato no tocan la red."""
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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(ORIGENES_DESARROLLO),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SoloEsteEquipo, permitidos=HOSTS_PERMITIDOS)

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

    app.include_router(router)

    if frontend is not None and (frontend / "index.html").exists():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app


app = crear_app()

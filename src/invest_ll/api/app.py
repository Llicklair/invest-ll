"""La aplicación FastAPI del panel: la API en `/api` y el frontend ya compilado en `/`.

Un solo proceso y un solo puerto (8601), como antes: el frontend de Next.js se exporta como
ficheros estáticos (`web/out`) y los sirve esta misma aplicación. Arrancar el panel sigue siendo
arrancar UNA cosa. En desarrollo, `npm run dev` en `web/` (puerto 3000) habla con esta API, y por
eso se permite ese origen y ninguno más.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from invest_ll.api.rutas import router
from invest_ll.errors import InvestLLError

RAIZ_REPO = Path(__file__).resolve().parents[3]
FRONTEND = RAIZ_REPO / "web" / "out"
ORIGENES_DESARROLLO = ("http://localhost:3000", "http://127.0.0.1:3000")


def crear_app(frontend: Path | None = FRONTEND) -> FastAPI:
    app = FastAPI(
        title="INVEST LL",
        description=(
            "El panel de INVEST LL. Arranca en simulacion; ninguna ruta envia ordenes salvo "
            "POST /api/ordenes, que exige la cantidad tecleada como confirmacion."
        ),
        version="1.0.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(ORIGENES_DESARROLLO),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(InvestLLError)
    async def _dominio(_: Request, error: InvestLLError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return JSONResponse(status_code=422, content={"detail": str(error)})

    app.include_router(router)

    if frontend is not None and (frontend / "index.html").exists():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app


app = crear_app()

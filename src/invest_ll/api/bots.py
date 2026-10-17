"""Bots con dinero ficticio, al estilo de los vaults de Hyperliquid (docs/panel-v3-vivo.md §3).

ESQUELETO DEL CONTRATO v3: rutas y modelos fijados; los cuerpos, pendientes. Nada sale al exterior.
"""

from __future__ import annotations

from fastapi import APIRouter

from invest_ll.api.schemas_v3 import Bots, DetalleBot, NuevoBot, Plantillas

router = APIRouter()

PENDIENTE = "pendiente de implementar"


@router.get("/bots/plantillas", tags=["bots"])
def plantillas() -> Plantillas:
    raise NotImplementedError(PENDIENTE)


@router.get("/bots", tags=["bots"])
def lista() -> Bots:
    """Todos los bots con lo que llevan generado, valorados a precios de ahora."""
    raise NotImplementedError(PENDIENTE)


@router.post("/bots", tags=["bots"], status_code=201)
def desplegar(nuevo: NuevoBot) -> DetalleBot:
    """Crea el bot y lo pone en marcha. 422 en llano si la plantilla, las monedas o los
    parámetros no valen."""
    raise NotImplementedError(PENDIENTE)


@router.get("/bots/{bot_id}", tags=["bots"])
def detalle(bot_id: str) -> DetalleBot:
    """404 si no existe."""
    raise NotImplementedError(PENDIENTE)


@router.post("/bots/{bot_id}/parar", tags=["bots"])
def parar(bot_id: str) -> DetalleBot:
    """Deja de operar; conserva sus posiciones (siguen valorándose)."""
    raise NotImplementedError(PENDIENTE)


@router.post("/bots/{bot_id}/reanudar", tags=["bots"])
def reanudar(bot_id: str) -> DetalleBot:
    raise NotImplementedError(PENDIENTE)


@router.delete("/bots/{bot_id}", tags=["bots"], status_code=204)
def borrar(bot_id: str) -> None:
    """Borra el bot y su registro. 404 si no existe."""
    raise NotImplementedError(PENDIENTE)

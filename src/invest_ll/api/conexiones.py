"""Conexiones con varios exchanges (docs/panel-v4-real.md §1 y §4).

ESQUELETO DEL CONTRATO v4: rutas y modelos fijados; los cuerpos, pendientes. Generaliza a cualquier
exchange lo que `api/conexion.py` hace con Binance (que sigue funcionando para el plan).
"""

from __future__ import annotations

from fastapi import APIRouter

from invest_ll.api.schemas_v4 import (
    ActivarExchange,
    ClavesExchange,
    Conexiones,
    EstadoExchange,
    ExchangeDisponible,
    MercadosExchange,
    PruebaExchange,
    RedExchange,
)

router = APIRouter()

PENDIENTE = "pendiente de implementar"


@router.get("/conexiones", tags=["conexiones"])
def conexiones() -> Conexiones:
    """Cada exchange con su estado, y la configuración del conector MCP para Claude."""
    raise NotImplementedError(PENDIENTE)


@router.get("/conexiones/disponibles", tags=["conexiones"])
def disponibles() -> list[ExchangeDisponible]:
    """Los exchanges que se pueden conectar, con los campos de sus claves y cómo conseguirlas."""
    raise NotImplementedError(PENDIENTE)


@router.put("/conexiones/{exchange}/claves/{red}", tags=["conexiones"], status_code=204)
def guardar_claves(exchange: str, red: RedExchange, claves: ClavesExchange) -> None:
    """Al almacén de credenciales de Windows. Nunca se devuelven. 422 en llano si falta algún campo
    o si las reales coinciden con las de pruebas."""
    raise NotImplementedError(PENDIENTE)


@router.delete("/conexiones/{exchange}/claves/{red}", tags=["conexiones"], status_code=204)
def borrar_claves(exchange: str, red: RedExchange) -> None:
    raise NotImplementedError(PENDIENTE)


@router.post("/conexiones/{exchange}/probar/{red}", tags=["conexiones"])
def probar(exchange: str, red: RedExchange) -> PruebaExchange:
    """Lee saldo y permisos con esas claves. No envía ninguna orden."""
    raise NotImplementedError(PENDIENTE)


@router.post("/conexiones/{exchange}/activar", tags=["conexiones"])
def activar(exchange: str, peticion: ActivarExchange) -> EstadoExchange:
    """Usa ese exchange en pruebas o en real. Real exige claves distintas, evidencia de pruebas
    (si el exchange tiene red de pruebas), que la clave no pueda retirar si se sabe, y 'DINERO
    REAL'. 422 en llano con lo que falte."""
    raise NotImplementedError(PENDIENTE)


@router.get("/conexiones/{exchange}/mercados", tags=["conexiones"])
def mercados(exchange: str, red: RedExchange = "real") -> MercadosExchange:
    """Los pares de contado del exchange (datos públicos: no necesita claves)."""
    raise NotImplementedError(PENDIENTE)

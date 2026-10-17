"""Estrategias a medida y diseñarlas con Claude (docs/panel-v4-real.md §2).

ESQUELETO DEL CONTRATO v4: rutas y modelos fijados; los cuerpos, pendientes. Una estrategia es un
JSON validado que el motor interpreta; nada se ejecuta como código.
"""

from __future__ import annotations

from fastapi import APIRouter

from invest_ll.api.schemas_v4 import (
    DetalleEstrategia,
    EsquemaEstrategia,
    Estrategias,
    NuevaEstrategia,
    PeticionDiseno,
    PeticionPruebaEstrategia,
    RespuestaDiseno,
    ResultadoPrueba,
)

router = APIRouter()

PENDIENTE = "pendiente de implementar"


@router.get("/medida", tags=["medida"])
def lista() -> Estrategias:
    raise NotImplementedError(PENDIENTE)


@router.get("/medida/esquema", tags=["medida"])
def esquema() -> EsquemaEstrategia:
    """El formato de las estrategias (JSON Schema), con ejemplos y su explicación."""
    raise NotImplementedError(PENDIENTE)


@router.post("/medida", tags=["medida"], status_code=201)
def guardar(nueva: NuevaEstrategia) -> DetalleEstrategia:
    """Valida y guarda (nueva estrategia o nueva versión). 422 en llano si no es válida."""
    raise NotImplementedError(PENDIENTE)


@router.get("/medida/{estrategia_id}", tags=["medida"])
def detalle(estrategia_id: str) -> DetalleEstrategia:
    raise NotImplementedError(PENDIENTE)


@router.delete("/medida/{estrategia_id}", tags=["medida"], status_code=204)
def borrar(estrategia_id: str) -> None:
    """409 si algún bot la usa."""
    raise NotImplementedError(PENDIENTE)


@router.post("/medida/{estrategia_id}/probar", tags=["medida"])
def probar(estrategia_id: str, peticion: PeticionPruebaEstrategia) -> ResultadoPrueba:
    """La prueba sobre el pasado con velas del exchange, costes y frente a mantener."""
    raise NotImplementedError(PENDIENTE)


@router.post("/medida/disenar", tags=["medida"])
def disenar(peticion: PeticionDiseno) -> RespuestaDiseno:
    """Un turno de la conversación con Claude (CLI `claude`, suscripción; gasta cuota). Claude usa
    el conector MCP: puede escribir, validar, probar y desplegar en ficticio; NUNCA activar real.
    Puede tardar un par de minutos. 422 si `claude` no está disponible."""
    raise NotImplementedError(PENDIENTE)


@router.get("/medida/disenar/{sesion}", tags=["medida"])
def conversacion(sesion: str) -> RespuestaDiseno:
    """La conversación guardada (404 si no existe)."""
    raise NotImplementedError(PENDIENTE)

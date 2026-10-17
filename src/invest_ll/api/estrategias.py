"""Estrategias: el catálogo en llano, tus números y la recomendación (docs/panel-v2.md, 4.2, 5, 6).

ESQUELETO DEL CONTRATO v2: rutas y modelos fijados; los cuerpos, pendientes.
"""

from __future__ import annotations

from fastapi import APIRouter

from invest_ll.api.schemas_v2 import (
    Catalogo,
    Perfil,
    PeticionSimulacion,
    Recomendacion,
    Simulacion,
)

router = APIRouter()

PENDIENTE = "pendiente de implementar"


@router.get("/estrategias", tags=["estrategias"])
def catalogo() -> Catalogo:
    """Las estrategias con su descripción llana y sus cifras calculadas sobre los datos."""
    raise NotImplementedError(PENDIENTE)


@router.post("/estrategias/simular", tags=["estrategias"])
def simular(peticion: PeticionSimulacion) -> Simulacion:
    """Inicial + mensual desde un año, en 1-4 estrategias. 404 si una clave no existe."""
    raise NotImplementedError(PENDIENTE)


@router.post("/estrategias/recomendar", tags=["estrategias"])
def recomendar(perfil: Perfil) -> Recomendacion:
    """Reglas fijas y explicables (docs/panel-v2.md, sección 6)."""
    raise NotImplementedError(PENDIENTE)

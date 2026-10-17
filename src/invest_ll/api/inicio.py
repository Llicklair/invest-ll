"""Inicio: cómo va tu dinero y qué tienes que hacer (docs/panel-v2.md, 4.1).

ESQUELETO DEL CONTRATO v2: ruta y modelo fijados; el cuerpo, pendiente.
"""

from __future__ import annotations

from fastapi import APIRouter

from invest_ll.api.schemas_v2 import Inicio

router = APIRouter()

PENDIENTE = "pendiente de implementar"


@router.get("/inicio", tags=["inicio"])
def inicio() -> Inicio:
    """Tu dinero hoy (cartera del modo activo), el plan resumido, acciones pendientes y avisos."""
    raise NotImplementedError(PENDIENTE)

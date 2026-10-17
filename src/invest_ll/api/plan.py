"""Tu plan y qué toca hacer hoy (docs/panel-v2.md, 4.2 paso 3, 4.3 y 7).

ESQUELETO DEL CONTRATO v2: rutas y modelos fijados; los cuerpos, pendientes.
"""

from __future__ import annotations

from fastapi import APIRouter

from invest_ll.api.schemas import MovimientoRegistrado
from invest_ll.api.schemas_v2 import AccionHecha, Hoy, NuevoPlan, PlanGuardado

router = APIRouter()

PENDIENTE = "pendiente de implementar"


@router.get("/plan", tags=["plan"])
def ver_plan() -> PlanGuardado:
    raise NotImplementedError(PENDIENTE)


@router.put("/plan", tags=["plan"])
def guardar_plan(plan: NuevoPlan) -> PlanGuardado:
    """422 si hay dos estrategias del mismo mercado o una clave desconocida o de laboratorio."""
    raise NotImplementedError(PENDIENTE)


@router.delete("/plan", tags=["plan"], status_code=204)
def borrar_plan() -> None:
    """404 si no había plan."""
    raise NotImplementedError(PENDIENTE)


@router.get("/plan/hoy", tags=["plan"])
def hoy() -> Hoy:
    """Qué toca hacer hoy según el plan y la cartera del modo activo. No envía nada."""
    raise NotImplementedError(PENDIENTE)


@router.post("/plan/hoy/{accion_id}/hecho", tags=["plan"], status_code=201)
def hecho(accion_id: str, hecha: AccionHecha) -> MovimientoRegistrado:
    """Anota en tu registro una compra hecha en tu bróker (solo acciones `donde=broker`)."""
    raise NotImplementedError(PENDIENTE)

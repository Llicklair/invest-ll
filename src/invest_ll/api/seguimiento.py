"""Pestaña Estimado vs real: lo estimado frente a lo que pasó.

Es la única evidencia sobre el LLM que no está contaminada: un backtest sobre el pasado no vale,
porque el modelo sabe lo que ocurrió después. Los fallos siguen en la tabla a propósito: un
historial que solo guarda los aciertos no mide nada.
"""

from __future__ import annotations

from fastapi import APIRouter

from invest_ll.api.schemas import FilaSeguimiento, Seguimiento
from invest_ll.tracking.forecast import build_track_record, pending
from invest_ll.tracking.store import ForecastStore

router = APIRouter()


@router.get("/seguimiento", tags=["seguimiento"])
def seguimiento() -> Seguimiento:
    almacen = ForecastStore()
    historial = build_track_record(almacen)
    return Seguimiento(
        evaluadas=historial.count,
        pendientes=len(pending(almacen)),
        sobreestimaciones=historial.overestimates,
        # Sin ninguna evaluada no hay veredicto que dar: "sin datos" no es una tendencia.
        tendencia=historial.tendency if historial.count else None,
        filas=[
            FilaSeguimiento(
                emitida=e.forecast.issued_at.date(),
                estimado=e.forecast.expected_value,
                real=e.outcome.actual_value,
                error=e.error,
            )
            for e in historial.evaluations
        ],
    )

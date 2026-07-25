"""Poner las estimaciones frente a lo que pasó."""

from __future__ import annotations

from typing import TYPE_CHECKING

from invest_ll.tracking.models import Evaluation, TrackRecord

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.tracking.store import ForecastStore


def build_track_record(store: ForecastStore) -> TrackRecord:
    """Cruza estimaciones con resultados.

    Las estimaciones **sin resultado todavía no cuentan**: incluirlas como aciertos o como fallos
    sería inventarse un dato. Una estimación cuyo horizonte no ha vencido no dice nada aún.
    """
    resultados = {o.forecast_id: o for o in store.outcomes()}
    evaluaciones = tuple(
        Evaluation(forecast=f, outcome=resultados[f.forecast_id])
        for f in store.forecasts()
        if f.forecast_id in resultados
    )
    return TrackRecord(evaluations=evaluaciones)


def pending(store: ForecastStore) -> list[str]:
    """Estimaciones emitidas que aún no tienen resultado."""
    resultados = {o.forecast_id for o in store.outcomes()}
    return [f.forecast_id for f in store.forecasts() if f.forecast_id not in resultados]

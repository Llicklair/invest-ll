"""Orquestación de la descarga (T027, T030, T040, T046, T052).

`now` y `sleep` se **inyectan**. No es purismo: descartar la vela en curso necesita saber qué hora
es, y reintentar necesita esperar. Leídos del sistema harían los tests dependientes de cuándo se
ejecutan y la suite lenta de verdad.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from invest_ll.data.series import PriceSeries
from invest_ll.fetch.errors import NoDataError, UnsupportedIntervalError
from invest_ll.fetch.merge import Discrepancy, drop_unclosed, merge, missing_ranges
from invest_ll.fetch.provenance import (
    Provenance,
    QualityWarning,
    WarningKind,
    warnings_from_capabilities,
)
from invest_ll.fetch.request import Market
from invest_ll.fetch.retry import with_retries
from invest_ll.fetch.store import HistoryStore, calendar_for

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.data.bar import Bar
    from invest_ll.fetch.protocol import MarketDataProvider
    from invest_ll.fetch.request import FetchRequest


# A partir de un dia, la pregunta al calendario es si hubo sesion, no si estaba abierto.
_UN_DIA = timedelta(days=1)


@dataclass(frozen=True, slots=True)
class FetchResult:
    """Lo que produce una descarga."""

    path: Path
    provenance: Provenance
    added_count: int
    discrepancies: tuple[Discrepancy, ...] = ()
    warnings: tuple[QualityWarning, ...] = ()
    requests_made: int = 0
    discrepancy_path: Path | None = None
    series: PriceSeries | None = field(default=None, repr=False)


def fetch_history(
    request: FetchRequest,
    provider: MarketDataProvider,
    store: HistoryStore,
    *,
    now: datetime,
    sleep: Callable[[float], None] = time.sleep,
) -> FetchResult:
    """Descarga el histórico pedido y lo deja listo para el motor.

    Nunca deja lo local peor que antes: si el proveedor falla, lo que había sigue estando.
    """
    capacidades = provider.capabilities

    if request.interval not in capacidades.supported_intervals:
        raise UnsupportedIntervalError(
            f"{capacidades.name} no ofrece la granularidad {request.interval.name}. "
            f"Disponibles: {sorted(i.name for i in capacidades.supported_intervals)}"
        )

    almacenado = store.load(request, capacidades.name)
    bars_previas: tuple[Bar, ...] = almacenado[0].bars if almacenado else ()

    tramos = missing_ranges(
        bars_previas or None,
        request.start,
        request.end,
        interval_duration=request.interval.duration,
    )

    descargadas: list[Bar] = []
    peticiones = 0
    for inicio, fin in tramos:
        lote = with_retries(
            lambda i=inicio, f=fin: provider.fetch(request.symbol, request.interval, i, f),
            sleep=sleep,
        )
        peticiones += 1
        descargadas.extend(lote)

    # La vela en curso se descarta siempre: guardarla como definitiva metería en el histórico un
    # dato que todavía va a cambiar (FR-007).
    cerradas = drop_unclosed(descargadas, interval_duration=request.interval.duration, now=now)

    resultado = merge(bars_previas or None, cerradas)

    if not resultado.bars:
        raise NoDataError(
            f"no hay datos para {request.symbol} entre {request.start.date()} y "
            f"{request.end.date()} con granularidad {request.interval.name}"
        )

    # La validación de la 001 se aplica aquí: si la serie no la pasa, no se guarda (FR-019).
    series = PriceSeries(
        symbol=request.symbol,
        interval=request.interval,
        calendar=calendar_for(request),
        bars=resultado.bars,
    )

    avisos = list(
        warnings_from_capabilities(capacidades, is_equity=request.market is Market.EQUITY)
    )
    avisos.extend(_gap_warnings(series))
    avisos.extend(_partial_range_warning(series, request))

    provenance = Provenance(
        provider=capacidades.name,
        symbol=request.symbol,
        interval=request.interval.name,
        market=request.market.value,
        downloaded_at=now,
        range_start=series.bars[0].timestamp,
        range_end=series.bars[-1].timestamp,
        bar_count=len(series),
        prices_adjusted=capacidades.adjusts_prices,
        quality_warnings=tuple(avisos),
    )

    ruta = store.save(request, series, provenance)

    # Las discrepancias se guardan aparte y jamás se aplican solas (FR-026).
    ruta_discrepancias: Path | None = None
    if resultado.discrepancies:
        ruta_discrepancias = store.save_discrepancies(request, capacidades.name, cerradas, now)

    return FetchResult(
        path=ruta,
        provenance=provenance,
        added_count=resultado.added_count,
        discrepancies=resultado.discrepancies,
        warnings=tuple(avisos),
        requests_made=peticiones,
        discrepancy_path=ruta_discrepancias,
        series=series,
    )


def verify_history(
    request: FetchRequest,
    provider: MarketDataProvider,
    store: HistoryStore,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[Discrepancy, ...]:
    """Reexamina un histórico completo contra el proveedor (FR-029).

    **Explícita y aparte** a propósito: hacerlo en cada descarga multiplicaría las peticiones y
    chocaría con FR-013. No modifica nada — solo informa.
    """
    almacenado = store.load(request, provider.capabilities.name)
    if almacenado is None:
        return ()

    series = almacenado[0]
    frescas = with_retries(
        lambda: provider.fetch(
            request.symbol,
            request.interval,
            series.bars[0].timestamp,
            series.bars[-1].timestamp + request.interval.duration,
        ),
        sleep=sleep,
    )
    return merge(series.bars, frescas).discrepancies


def _gap_warnings(series: PriceSeries) -> list[QualityWarning]:
    """Reutiliza la detección de huecos de la 001 en lugar de reimplementarla."""
    from invest_ll.data.loader import detect_gaps

    return [
        QualityWarning(kind=WarningKind.GAP, message=aviso.message) for aviso in detect_gaps(series)
    ]


def _hay_sesion_entre(series: PriceSeries, desde: datetime, hasta: datetime) -> bool:
    """¿Hubo algún periodo negociable en este tramo?

    Si no lo hubo, que el proveedor no traiga datos ahí no es un fallo suyo: es que el mercado
    estaba cerrado.
    """
    if desde >= hasta:
        return False

    paso = series.interval.duration
    negociable = series.calendar.is_session if paso >= _UN_DIA else series.calendar.is_open

    momento = desde
    while momento < hasta:
        if negociable(momento):
            return True
        momento += paso
    return False


def _partial_range_warning(series: PriceSeries, request: FetchRequest) -> list[QualityWarning]:
    """Avisa cuando el proveedor cubre menos de lo pedido.

    Sin este aviso, el operador creería estar evaluando un periodo que en realidad no tiene.

    **Pero solo si falta algo de verdad.** Pedir desde el 1 de enero y recibir desde el 2 no es
    cobertura parcial: el 1 de enero no hubo sesión. Un aviso que salta en cada descarga es ruido,
    y el ruido hace que se ignoren los avisos que sí importan.
    """
    cubre_desde = series.bars[0].timestamp
    cubre_hasta = series.bars[-1].timestamp + request.interval.duration

    falta_al_principio = _hay_sesion_entre(series, request.start, cubre_desde)
    falta_al_final = _hay_sesion_entre(series, cubre_hasta, request.end)

    if not falta_al_principio and not falta_al_final:
        return []

    return [
        QualityWarning(
            kind=WarningKind.PARTIAL_RANGE,
            message=(
                f"el proveedor solo cubre de {cubre_desde.date()} a {cubre_hasta.date()}, "
                f"menos de lo pedido ({request.start.date()} a {request.end.date()}). "
                "El periodo evaluado no es el que creias."
            ),
        )
    ]


def as_data_warnings(avisos: Sequence[QualityWarning]) -> tuple[object, ...]:
    """Puente hacia el informe de la feature 001."""
    from invest_ll.fetch.provenance import as_data_warnings as convertir

    return convertir(avisos)

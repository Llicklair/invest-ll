"""Mercado en vivo de Hyperliquid (docs/panel-v3-vivo.md §1 y §5).

ESQUELETO DEL CONTRATO v3: rutas y modelos fijados; los cuerpos, pendientes. Solo lee datos
públicos de mercado; no envía nada a ningún exchange.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from invest_ll.api.schemas_v3 import EstadoVivo, LibroVivo, Monedas, Operaciones, Velas

router = APIRouter()

PENDIENTE = "pendiente de implementar"


@router.get("/vivo/estado", tags=["vivo"])
def estado_vivo() -> EstadoVivo:
    """Si llegan datos de Hyperliquid y desde cuándo."""
    raise NotImplementedError(PENDIENTE)


@router.get("/vivo/monedas", tags=["vivo"])
def monedas() -> Monedas:
    """Todas las monedas con su precio, variación y volumen de 24 h; las más negociadas primero."""
    raise NotImplementedError(PENDIENTE)


@router.get("/vivo/libro", tags=["vivo"])
def libro(coin: str) -> LibroVivo:
    """El libro de órdenes de la moneda (empieza a seguirla si no se seguía). 404 si no existe."""
    raise NotImplementedError(PENDIENTE)


@router.get("/vivo/operaciones", tags=["vivo"])
def operaciones(coin: str) -> Operaciones:
    """Las últimas operaciones de la moneda."""
    raise NotImplementedError(PENDIENTE)


@router.get("/vivo/velas", tags=["vivo"])
def velas(
    coin: str, intervalo: str = "1h", limite: int = Query(default=300, ge=1, le=5000)
) -> Velas:
    """Velas de la moneda; la última puede estar en curso. 422 si el intervalo no existe."""
    raise NotImplementedError(PENDIENTE)


@router.get("/vivo/stream", tags=["vivo"], response_class=StreamingResponse)
def stream(
    coin: str | None = None,
    intervalo: str = "1h",
    canales: str = "monedas,libro,operaciones,vela,cuenta,bots,estado",
) -> StreamingResponse:
    """Server-Sent Events: cada evento lleva el JSON de su ruta REST (docs/panel-v3-vivo.md §5)."""
    raise NotImplementedError(PENDIENTE)

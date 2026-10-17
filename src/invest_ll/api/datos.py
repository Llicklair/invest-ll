"""Datos al día sin abrir una terminal (contrato v2.1).

ESQUELETO DEL CONTRATO: rutas y modelos fijados; los cuerpos, pendientes.

Una sola actualización trae TODO lo que usa el panel: los históricos de `data/market/<proveedor>/`
(Mercado, Laboratorio), los fondos (`invest-ll-quant download --etf`) y el universo de Binance
(`invest-ll-quant download`), en segundo plano y paso a paso. Solo lee datos públicos de mercado:
nunca envía nada.
"""

from __future__ import annotations

from fastapi import APIRouter

from invest_ll.api.schemas_v2 import EstadoDatos

router = APIRouter()

PENDIENTE = "pendiente de implementar"


@router.get("/datos", tags=["datos"])
def estado_datos() -> EstadoDatos:
    """De cuándo son los datos que usa el panel y cómo va la última actualización."""
    raise NotImplementedError(PENDIENTE)


@router.post("/datos/actualizar", tags=["datos"], status_code=202)
def actualizar_datos() -> EstadoDatos:
    """Empieza a actualizarlo todo en segundo plano. 409 si ya hay una actualización en marcha."""
    raise NotImplementedError(PENDIENTE)

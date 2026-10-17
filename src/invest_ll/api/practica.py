"""Cuenta de práctica: comprar y vender con dinero ficticio a precios reales (docs/panel-v3-vivo.md §2).

ESQUELETO DEL CONTRATO v3: rutas y modelos fijados; los cuerpos, pendientes. Nada sale al exterior:
las órdenes se ejecutan con `invest_ll.vivo.ejecucion` contra el libro real del momento.
"""

from __future__ import annotations

from fastapi import APIRouter

from invest_ll.api.schemas_v3 import (
    CuentaPractica,
    NuevaOrdenPractica,
    ReinicioPractica,
    ResultadoPractica,
)

router = APIRouter()

PENDIENTE = "pendiente de implementar"


@router.get("/practica", tags=["practica"])
def cuenta() -> CuentaPractica:
    """La cuenta de práctica valorada a precios de ahora."""
    raise NotImplementedError(PENDIENTE)


@router.post("/practica/ordenes", tags=["practica"])
def nueva_orden(orden: NuevaOrdenPractica) -> ResultadoPractica:
    """A mercado se ejecuta ya contra el libro; con límite queda pendiente. 422 en llano si no hay
    saldo, si no tienes esa moneda o si el libro no da para tanto."""
    raise NotImplementedError(PENDIENTE)


@router.delete("/practica/ordenes/{orden_id}", tags=["practica"])
def cancelar(orden_id: str) -> CuentaPractica:
    """Cancela una orden con límite pendiente. 404 si no existe."""
    raise NotImplementedError(PENDIENTE)


@router.post("/practica/reiniciar", tags=["practica"])
def reiniciar(reinicio: ReinicioPractica) -> CuentaPractica:
    """Empieza de cero con ese saldo ficticio (el historial anterior se guarda aparte)."""
    raise NotImplementedError(PENDIENTE)

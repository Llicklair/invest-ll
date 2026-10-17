"""Anotar en el registro de órdenes (`ledger/`) una orden de un conector, con su exchange y su bot.

Es lo que deja la **evidencia** que piden los cerrojos de real (`activacion`: una orden de pruebas
de ese exchange, ejecutada) y lo que lee la cartera de cada modo. Un sitio para hacerlo bien:

- el modo se escribe como lo lee el resto del sistema: "pruebas" o "REAL" (`NOMBRE_EN_EL_REGISTRO`);
- la comisión, en la moneda en la que se cuenta (la cotizada del par): si el exchange la cobró en
  la moneda comprada se pasa con el precio de la orden; si fue en otra (BNB), `None` ("no se
  sabe"), que la cartera avisa en vez de contar cero;
- una orden que aún puede cambiar (abierta) no se anota: se anota cuando se resuelve.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from invest_ll.live.broker import OrderRequest, OrderResult, OrderStatus, Side
from invest_ll.live.ledger import ExecutionLedger
from invest_ll.live.modo_panel import NOMBRE_EN_EL_REGISTRO

if TYPE_CHECKING:  # pragma: no cover
    from decimal import Decimal

    from invest_ll.exchanges.conector import OrdenExchange, Red
    from invest_ll.live.ledger import LedgerEntry


def resultado_de(orden: OrdenExchange) -> OrderResult:
    """La orden del conector como `OrderResult` del registro. `ValueError` si aún está abierta."""
    if orden.estado == "abierta" or (orden.estado == "parcial" and orden.ejecutada == 0):
        raise ValueError(
            f"La orden {orden.id_cliente} sigue abierta: se anota cuando se ejecute o se cancele."
        )
    if orden.estado == "desconocido":
        estado = OrderStatus.UNKNOWN
    elif orden.ejecutada <= 0:
        estado = OrderStatus.REJECTED
    elif orden.estado == "ejecutada" and orden.ejecutada >= orden.cantidad:
        estado = OrderStatus.FILLED
    else:
        estado = OrderStatus.PARTIAL
    return OrderResult(
        request=OrderRequest(
            symbol=orden.par,
            side=Side.BUY if orden.lado == "compra" else Side.SELL,
            quantity=orden.cantidad,
            requested_at=orden.at,
        ),
        status=estado,
        filled_quantity=orden.ejecutada,
        fill_price=orden.precio_medio,
        executed_at=orden.at if orden.ejecutada > 0 else None,
        broker_reference=orden.id_exchange,
        commission=comision_en_la_cotizada(orden),
    )


def comision_en_la_cotizada(orden: OrdenExchange) -> Decimal | None:
    """La comisión en la moneda cotizada del par (USDT en BTC/USDT), o `None` si no se puede."""
    if orden.comision is None or orden.comision_moneda is None:
        return None
    base, _, cotizada = orden.par.partition("/")
    if orden.comision_moneda == cotizada:
        return orden.comision
    if orden.comision_moneda == base and orden.precio_medio is not None:
        return orden.comision * orden.precio_medio
    return None


def anotar(
    orden: OrdenExchange,
    *,
    exchange: str,
    red: Red,
    bot: str | None = None,
    ledger: ExecutionLedger | None = None,
) -> LedgerEntry:
    """Anota la orden en el registro con su modo, su exchange y su bot."""
    return (ledger or ExecutionLedger()).record(
        resultado_de(orden), mode_name=NOMBRE_EN_EL_REGISTRO[red], exchange=exchange, bot=bot
    )

"""Órdenes, operaciones y aplicación de la fricción (T030).

El precio de referencia y el precio efectivo se guardan por separado a propósito: sin esa
distinción no se puede decir cuánto costó el slippage, y el Principio IV exige poder decirlo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

CENT = Decimal("0.00000001")


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    FILLED = "filled"
    PARTIAL = "partial"
    REJECTED = "rejected"


class ExitReason(Enum):
    """Por qué se cerró una posición (FR-031)."""

    SIGNAL = "signal"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    END_OF_SERIES = "end_of_series"


@dataclass(frozen=True, slots=True)
class Order:
    """Intento de ejecutar una señal.

    `execution_timestamp` es **siempre** posterior a `signal_timestamp`. Ese invariante es la
    huella en datos del Principio II: se puede auditar sobre el informe ya emitido (SC-008).
    """

    signal_timestamp: datetime
    execution_timestamp: datetime
    side: OrderSide
    reference_price: Decimal
    fill_price: Decimal
    requested_quantity: Decimal
    filled_quantity: Decimal
    commission: Decimal
    slippage_cost: Decimal
    status: OrderStatus
    rejection_reason: str | None = None

    @property
    def costs(self) -> Decimal:
        return self.commission + self.slippage_cost

    @property
    def notional(self) -> Decimal:
        return self.filled_quantity * self.fill_price


@dataclass(frozen=True, slots=True)
class Trade:
    """Ciclo completo de entrada y salida del mercado."""

    entry_order: Order
    exit_order: Order | None
    exit_reason: ExitReason
    gross_pnl: Decimal
    costs: Decimal

    @property
    def net_pnl(self) -> Decimal:
        return self.gross_pnl - self.costs

    @property
    def is_win(self) -> bool:
        return self.net_pnl > 0


def apply_slippage(price: Decimal, side: OrderSide, rate: Decimal) -> Decimal:
    """El slippage siempre juega en contra: se compra más caro y se vende más barato.

    Modelarlo a favor en algún caso sería inventar un mercado amable que no existe.
    """
    factor = (1 + rate) if side is OrderSide.BUY else (1 - rate)
    return (price * factor).quantize(CENT)


def build_order(
    *,
    signal_timestamp: datetime,
    execution_timestamp: datetime,
    side: OrderSide,
    reference_price: Decimal,
    quantity: Decimal,
    commission_rate: Decimal,
    slippage_rate: Decimal,
) -> Order:
    """Construye una orden ejecutada aplicando la fricción configurada."""
    fill_price = apply_slippage(reference_price, side, slippage_rate)
    slippage_cost = (abs(fill_price - reference_price) * quantity).quantize(CENT)
    commission = (fill_price * quantity * commission_rate).quantize(CENT)

    return Order(
        signal_timestamp=signal_timestamp,
        execution_timestamp=execution_timestamp,
        side=side,
        reference_price=reference_price,
        fill_price=fill_price,
        requested_quantity=quantity,
        filled_quantity=quantity,
        commission=commission,
        slippage_cost=slippage_cost,
        status=OrderStatus.FILLED,
    )


def rejected_order(
    *,
    signal_timestamp: datetime,
    execution_timestamp: datetime,
    side: OrderSide,
    reference_price: Decimal,
    requested_quantity: Decimal,
    reason: str,
) -> Order:
    """Orden que el mercado simulado no ejecuta. La simulación continúa (FR-009)."""
    return Order(
        signal_timestamp=signal_timestamp,
        execution_timestamp=execution_timestamp,
        side=side,
        reference_price=reference_price,
        fill_price=reference_price,
        requested_quantity=requested_quantity,
        filled_quantity=Decimal(0),
        commission=Decimal(0),
        slippage_cost=Decimal(0),
        status=OrderStatus.REJECTED,
        rejection_reason=reason,
    )

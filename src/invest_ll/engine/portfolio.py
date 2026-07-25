"""Estado de la cartera simulada (T029).

Es el único estado mutable del motor, y **nunca se muestra a la estrategia**. Si una estrategia
pudiera ver el capital, podría condicionar su decisión a él y dos estrategias dejarían de ser
comparables sobre los mismos datos (Principio V).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from invest_ll.engine.execution import Order


@dataclass(frozen=True, slots=True)
class Position:
    """Exposición abierta al mercado. En v1 solo puede haber una, y siempre larga."""

    entry_order: Order
    quantity: Decimal
    entry_price: Decimal
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None

    def value_at(self, price: Decimal) -> Decimal:
        return self.quantity * price


def _no_equity() -> list[Decimal]:
    return []


def _no_timestamps() -> list[datetime]:
    return []


@dataclass(slots=True)
class PortfolioState:
    """Caja, posición abierta y curva de patrimonio."""

    cash: Decimal
    position: Position | None = None
    equity_curve: list[Decimal] = field(default_factory=_no_equity)
    equity_timestamps: list[datetime] = field(default_factory=_no_timestamps)

    @property
    def is_open(self) -> bool:
        return self.position is not None

    def equity(self, price: Decimal) -> Decimal:
        """Patrimonio total: caja más el valor de mercado de la posición abierta."""
        if self.position is None:
            return self.cash
        return self.cash + self.position.value_at(price)

    def record_equity(self, moment: datetime, price: Decimal) -> None:
        self.equity_curve.append(self.equity(price))
        self.equity_timestamps.append(moment)

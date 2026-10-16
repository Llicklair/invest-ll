"""Spanish tax on crypto gains, as an account would actually pay it.

Every sale realises a gain or loss, including a swap from one coin to another (Hacienda treats it
as a permuta). Lots are matched first in, first out per asset. Gains and losses of a calendar year
are netted in the savings base; a net loss carries forward for four years. The tax for year Y is
paid at the end of June of Y+1, out of the account, which is when a rotating strategy's compounding
actually loses it.

Simplifications, stated so nobody mistakes this for tax advice: no other income in the savings base,
no two-month repurchase rule, no regional differences, the 2025 scale is applied to every year, and
amounts in USDT are taxed as if they were euros (no exchange-rate conversion).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

# Base del ahorro, scale in force from 2025: (upper bound of the bracket in EUR, rate).
SAVINGS_SCALE: tuple[tuple[float, float], ...] = (
    (6_000.0, 0.19),
    (50_000.0, 0.21),
    (200_000.0, 0.23),
    (300_000.0, 0.27),
    (float("inf"), 0.30),
)
CARRY_FORWARD_YEARS = 4


def savings_tax(base: float, scale: tuple[tuple[float, float], ...] = SAVINGS_SCALE) -> float:
    """Tax due on a positive savings base."""
    if base <= 0:
        return 0.0
    tax, lower = 0.0, 0.0
    for upper, rate in scale:
        if base <= lower:
            break
        tax += (min(base, upper) - lower) * rate
        lower = upper
    return tax


@dataclass(slots=True)
class _Lot:
    quantity: float
    unit_cost: float


@dataclass(slots=True)
class FifoTaxBook:
    """FIFO lots per instrument and realised gains per calendar year."""

    lots: dict[str, deque[_Lot]] = field(default_factory=lambda: dict[str, deque[_Lot]]())
    realised: dict[int, float] = field(default_factory=lambda: dict[int, float]())
    carried_losses: list[tuple[int, float]] = field(
        default_factory=lambda: list[tuple[int, float]]()
    )

    def buy(self, symbol: str, quantity: float, total_cost: float) -> None:
        """Record a purchase; `total_cost` includes fees, which raise the acquisition value."""
        if quantity <= 0:
            return
        self.lots.setdefault(symbol, deque()).append(_Lot(quantity, total_cost / quantity))

    def sell(self, symbol: str, quantity: float, net_proceeds: float, year: int) -> float:
        """Record a sale; `net_proceeds` is after fees. Returns the realised gain (or loss)."""
        if quantity <= 0:
            return 0.0
        queue = self.lots.get(symbol, deque())
        remaining, cost = quantity, 0.0
        while remaining > 1e-15 and queue:
            lot = queue[0]
            take = min(remaining, lot.quantity)
            cost += take * lot.unit_cost
            lot.quantity -= take
            remaining -= take
            if lot.quantity <= 1e-15:
                queue.popleft()
        if remaining > 1e-9 * max(quantity, 1.0):
            raise ValueError(f"selling {quantity} {symbol} but only {quantity - remaining} held")
        gain = net_proceeds - cost
        self.realised[year] = self.realised.get(year, 0.0) + gain
        return gain

    def tax_for_year(self, year: int) -> float:
        """Close the year: net it, apply carried losses (oldest first), return the tax due."""
        net = self.realised.get(year, 0.0)
        self.carried_losses = [
            (y, loss) for y, loss in self.carried_losses if year - y <= CARRY_FORWARD_YEARS
        ]
        if net < 0:
            self.carried_losses.append((year, -net))
            return 0.0
        remaining = net
        updated: list[tuple[int, float]] = []
        for y, loss in self.carried_losses:
            used = min(loss, remaining)
            remaining -= used
            if loss - used > 1e-9:
                updated.append((y, loss - used))
        self.carried_losses = updated
        return savings_tax(remaining)

"""Simulate a target-weight strategy on a panel, with every cost a real account would pay.

Timeline of each day `t`:

1. Instruments held whose data has ended (delisted, or a reused ticker's first life) are sold at
   their last close, minus `delist_haircut`.
2. Targets decided at the close of `t-1` are traded at the open of `t`. Sells go first; buys are
   scaled down if fees would overdraw the cash. Instruments with no open that day cannot trade.
3. The account is marked at the close.
4. If it is the first day of July, the Spanish tax of the previous year leaves the account
   (selling pro rata when cash is short), when `pay_tax` is on.
5. On decision days, the strategy sees the market up to this close and sets new targets.

**Tranches.** A weekly rule is hostage to its weekday: the same INVEST LL policy ended between
6,581 and 11,488 (from 10,000) depending only on the day it decided. With `tranches=k`, `k` copies
of the strategy decide on staggered days and the account trades to the average of their latest
targets. The timing luck averages out, and opposite trades between copies net inside one account.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np

from invest_ll.quant.panel import FloatArray, IntArray, Panel
from invest_ll.quant.strategies import WeightStrategy
from invest_ll.quant.tax import FifoTaxBook
from invest_ll.quant.universe import PointInTimeUniverse
from invest_ll.quant.view import MarketView

TAX_PAYMENT_MONTH = 7  # tax for year Y leaves the account on the first day of July of Y+1


@dataclass(frozen=True, slots=True)
class Costs:
    """Trading frictions. No defaults for the two that matter (Principle IV of the constitution).

    - `commission`, `slippage`: fraction of traded value paid per side.
    - `impact`: extra slippage that grows with order size relative to the instrument's typical
      daily volume, `impact * sqrt(order / median_daily_volume)`. Negligible for a small account,
      decisive for a large one: it is what caps the capacity of a strategy.
    - `min_trade`: orders below this value are skipped (exchange minimums, and pointless churn).
    - `delist_haircut`: fraction lost when a held instrument stops trading.
    """

    commission: float
    slippage: float
    impact: float = 0.1
    min_trade: float = 10.0
    delist_haircut: float = 0.0

    def __post_init__(self) -> None:
        if min(self.commission, self.slippage, self.impact, self.min_trade) < 0:
            raise ValueError("costs cannot be negative")
        if not 0 <= self.delist_haircut <= 1:
            raise ValueError("delist_haircut must be within [0, 1]")


# Binance spot, standard tier, paying fees in USDT: 0.1% per side (checked against the API in
# INVEST LL's docs). 0.05% slippage matches the project's existing assumption for liquid pairs.
BINANCE_SPOT = Costs(commission=0.001, slippage=0.0005)


@dataclass(frozen=True, slots=True)
class RunConfig:
    initial_capital: float
    rebalance_every: int = 7
    tranches: int = 1
    no_trade_band: float = 0.0
    start: int = 0
    pay_tax: bool = False

    def __post_init__(self) -> None:
        if self.initial_capital <= 0:
            raise ValueError("initial capital must be positive")
        if self.rebalance_every < 1 or not 1 <= self.tranches <= self.rebalance_every:
            raise ValueError("need rebalance_every >= 1 and 1 <= tranches <= rebalance_every")
        if not 0 <= self.no_trade_band < 1:
            raise ValueError("no_trade_band must be within [0, 1)")


@dataclass(frozen=True, slots=True)
class RunResult:
    name: str
    days: IntArray
    equity: FloatArray
    weights: FloatArray
    turnover: FloatArray
    costs: FloatArray
    taxes: FloatArray
    trades: int
    symbols: tuple[str, ...]
    periods_per_year: int
    final_after_liquidation_tax: float
    start: int = 0
    notes: tuple[str, ...] = field(default=())

    @property
    def returns(self) -> FloatArray:
        """Daily returns from the first active row (the row before is the starting capital)."""
        eq = self.equity[self.start :]
        return eq[1:] / eq[:-1] - 1.0

    @property
    def exposure(self) -> FloatArray:
        return self.weights[self.start :].sum(axis=1)


def _year_of(day: int) -> int:
    return datetime.fromtimestamp(day * 86_400, UTC).year


def _month_of(day: int) -> int:
    return datetime.fromtimestamp(day * 86_400, UTC).month


def run(
    panel: Panel,
    strategy: WeightStrategy | list[WeightStrategy],
    costs: Costs,
    config: RunConfig,
    universe: PointInTimeUniverse | None = None,
    name: str | None = None,
) -> RunResult:
    """Run a strategy (or one instance per tranche, for stateful strategies) over the panel."""
    copies = strategy if isinstance(strategy, list) else [strategy] * config.tranches
    if len(copies) != config.tranches:
        raise ValueError("pass one strategy instance per tranche")

    t_count, n = len(panel), len(panel.symbols)
    cash = float(config.initial_capital)
    qty = np.zeros(n)
    last_px = np.full(n, np.nan)
    book = FifoTaxBook()
    tranche_targets: list[FloatArray | None] = [None] * config.tranches
    pending: FloatArray | None = None
    offset = max(1, config.rebalance_every // config.tranches)

    equity = np.full(t_count, float(config.initial_capital))
    weights = np.zeros((t_count, n))
    turnover = np.zeros(t_count)
    cost_paid = np.zeros(t_count)
    tax_paid = np.zeros(t_count)
    trades = 0
    years_closed: set[int] = set()
    notes: list[str] = []

    def sell(col: int, quantity: float, price: float, rate: float, t: int) -> float:
        nonlocal cash, trades
        gross = quantity * price
        fee = gross * rate
        cash += gross - fee
        qty[col] -= quantity
        if qty[col] < 1e-12:
            qty[col] = 0.0
        book.sell(panel.symbols[col], quantity, gross - fee, _year_of(int(panel.days[t])))
        trades += 1
        return fee

    def raise_cash(due: float, t: int) -> float:
        """Sell holdings pro rata at the close until cash covers `due`. Returns the fees."""
        shortfall = due - cash
        if shortfall <= 0:
            return 0.0
        rate = costs.commission + costs.slippage
        held = np.nonzero(qty > 0)[0]
        value = float(np.sum(qty[held] * last_px[held]))
        if value <= 0:
            return 0.0
        fraction = min(1.0, shortfall / (value * (1.0 - rate)))
        fees = 0.0
        for col in held:
            fees += sell(int(col), float(qty[col]) * fraction, float(last_px[col]), rate, t)
        return fees

    for t in range(t_count):
        day = int(panel.days[t])
        o = panel.open[t]
        c = panel.close[t]

        # 1. Delisted holdings: out at the last close.
        dead = (qty > 0) & (panel.last_valid < t)
        for col in np.nonzero(dead)[0]:
            price = float(last_px[col]) * (1.0 - costs.delist_haircut)
            cost_paid[t] += sell(int(col), float(qty[col]), price, costs.commission, t)
            notes.append(
                f"{panel.date_at(t)}: {panel.symbols[col]} stopped trading, sold at last close"
            )

        # 2. Execute targets decided at yesterday's close, at today's open.
        if pending is not None:
            px = np.where(np.isnan(o), last_px, o)
            tradable = ~np.isnan(o)
            holdings = qty * np.nan_to_num(px)
            value = cash + float(holdings.sum())
            current_w = holdings / value if value > 0 else np.zeros(n)
            target_w = np.where(tradable, pending, current_w)
            change = target_w - current_w
            change[np.abs(change) < config.no_trade_band] = 0.0
            delta = change * value
            delta[np.abs(delta) < costs.min_trade] = 0.0
            # Liquidate fully when the target is zero, so no dust is left behind.
            full_exit = tradable & (pending <= 0) & (qty > 0) & (delta < 0)
            rates = costs.commission + _slippage(panel, t, delta, costs)

            traded_value = 0.0
            for col in np.nonzero(delta < 0)[0]:
                price = float(o[col])
                quantity = (
                    float(qty[col]) if full_exit[col] else min(float(qty[col]), -delta[col] / price)
                )
                traded_value += quantity * price
                cost_paid[t] += sell(int(col), quantity, price, float(rates[col]), t)

            buys = np.nonzero(delta > 0)[0]
            need = float(np.sum(delta[buys] * (1.0 + rates[buys])))
            scale = min(1.0, cash / need) if need > 0 else 0.0
            for col in buys:
                spend = float(delta[col]) * scale
                if spend < costs.min_trade:
                    continue
                fee = spend * float(rates[col])
                quantity = spend / float(o[col])
                qty[col] += quantity
                cash -= spend + fee
                cost_paid[t] += fee
                traded_value += spend
                book.buy(panel.symbols[col], quantity, spend + fee)
                trades += 1
            turnover[t] = traded_value / value if value > 0 else 0.0
            pending = None

        # 3. Mark to market.
        last_px = np.where(np.isnan(c), last_px, c)
        holdings = qty * np.nan_to_num(last_px)
        equity[t] = cash + float(holdings.sum())

        # 4. Tax for the previous year, paid in July.
        if config.pay_tax and _month_of(day) >= TAX_PAYMENT_MONTH:
            year = _year_of(day) - 1
            if year not in years_closed and book.realised:
                for y in range(min(book.realised), year + 1):
                    if y not in years_closed:
                        due = book.tax_for_year(y)
                        years_closed.add(y)
                        if due > 0:
                            cost_paid[t] += raise_cash(due, t)
                            cash -= due
                            tax_paid[t] += due
                holdings = qty * np.nan_to_num(last_px)
                equity[t] = cash + float(holdings.sum())

        weights[t] = holdings / equity[t] if equity[t] > 0 else 0.0

        # 5. Decisions at the close.
        if t >= config.start and t < t_count - 1:
            since = t - config.start
            changed = False
            for j, strat in enumerate(copies):
                if (since - j * offset) % config.rebalance_every == 0 and since >= j * offset:
                    target = strat.weights(MarketView(panel, t, universe))
                    if target is not None:
                        tranche_targets[j] = _clean(target)
                        changed = True
            if changed:
                # Copies that have not decided yet keep their share in cash until they do.
                active = [x for x in tranche_targets if x is not None]
                pending = np.sum(np.vstack(active), axis=0) / config.tranches

    final_tax = _liquidation_tax(book, qty, last_px, costs, panel, years_closed, config)
    return RunResult(
        name=name or strategy_name(copies[0]),
        days=panel.days,
        equity=equity,
        weights=weights,
        turnover=turnover,
        costs=cost_paid,
        taxes=tax_paid,
        trades=trades,
        symbols=panel.symbols,
        periods_per_year=panel.periods_per_year,
        final_after_liquidation_tax=float(equity[-1]) - final_tax,
        start=config.start,
        notes=tuple(notes),
    )


def strategy_name(strategy: WeightStrategy) -> str:
    return strategy.name


def _clean(target: FloatArray) -> FloatArray:
    w = np.nan_to_num(np.asarray(target, dtype=np.float64), nan=0.0)
    w = np.clip(w, 0.0, None)
    total = float(w.sum())
    if total > 1.0 + 1e-9:
        w = w / total
    return w


def _slippage(panel: Panel, t: int, delta: FloatArray, costs: Costs) -> FloatArray:
    """Per-instrument slippage for today's orders: base plus a square-root impact term."""
    base = np.full(len(delta), costs.slippage)
    if costs.impact <= 0:
        return base
    active = np.nonzero(delta != 0)[0]
    if len(active) == 0:
        return base
    lo = max(0, t - 30)
    window = panel.quote_volume[lo:t, active] if t > 0 else np.full((1, len(active)), np.nan)
    with np.errstate(all="ignore"):
        adv = np.nanmedian(window, axis=0) if len(window) else np.full(len(active), np.nan)
    adv = np.where(np.isnan(adv) | (adv <= 0), np.inf, adv)
    base[active] += costs.impact * np.sqrt(np.abs(delta[active]) / adv)
    return base


def _liquidation_tax(
    book: FifoTaxBook,
    qty: FloatArray,
    last_px: FloatArray,
    costs: Costs,
    panel: Panel,
    years_closed: set[int],
    config: RunConfig,
) -> float:
    """Tax still owed if everything were sold at the last close (for comparisons with holding)."""
    if len(panel) == 0:
        return 0.0
    year = _year_of(int(panel.days[-1]))
    for col in np.nonzero(qty > 0)[0]:
        price = float(last_px[col])
        gross = float(qty[col]) * price
        net = gross * (1.0 - costs.commission - costs.slippage)
        book.sell(panel.symbols[col], float(qty[col]), net, year)
    owed = 0.0
    first = min(book.realised) if book.realised else year
    for y in range(first, year + 1):
        if y not in years_closed:
            owed += book.tax_for_year(y)
    del config
    return owed


def annualisation(periods_per_year: int) -> float:
    return math.sqrt(periods_per_year)

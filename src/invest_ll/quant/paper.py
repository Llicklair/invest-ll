"""Forward test: record today's target portfolio, measure it later against what happened.

A backtest can always be fitted to the past; a record written before the future happens cannot. Each
`record` call appends the pre-registered portfolio's targets as of the latest close to a JSON Lines
file. `replay` runs the engine over the days since the first record, trading at the next open to
whatever was recorded, so the forward result carries the same costs as the backtest.

Records are append-only and carry the date of the data they used. Re-recording the same date is
refused rather than overwritten: an edited forecast is not a forecast.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from invest_ll.quant.engine import BINANCE_SPOT, Costs, RunConfig, RunResult, run
from invest_ll.quant.panel import FloatArray, Panel
from invest_ll.quant.strategies import WeightStrategy
from invest_ll.quant.universe import PointInTimeUniverse, UniverseRule
from invest_ll.quant.view import MarketView

DEFAULT_LEDGER = Path("paper/momentum.jsonl")


@dataclass(frozen=True, slots=True)
class PaperVariant:
    """One portfolio under forward test: its strategy, its ledger and its execution band."""

    key: str
    strategy: WeightStrategy
    ledger: Path
    no_trade_band: float = 0.0


def variants() -> dict[str, PaperVariant]:
    """The three candidates run forward side by side: pre-registered, stage two, and BTC trend."""
    from invest_ll.quant.strategies import MarketFilter, TrendAsset
    from invest_ll.quant.study import FLAGSHIP, NO_TRADE_BAND

    return {
        "preregistered": PaperVariant("preregistered", FLAGSHIP, DEFAULT_LEDGER),
        "filtered": PaperVariant(
            "filtered",
            MarketFilter(FLAGSHIP),
            Path("paper/momentum-filtered.jsonl"),
            NO_TRADE_BAND,
        ),
        "btc-trend": PaperVariant(
            "btc-trend", TrendAsset("BTCUSDT", 30), Path("paper/btc-trend.jsonl")
        ),
    }


@dataclass(frozen=True, slots=True)
class PaperRecord:
    data_date: str
    strategy: str
    weights: dict[str, float]
    closes: dict[str, float]


def current_targets(
    panel: Panel,
    strategy: WeightStrategy,
    rule: UniverseRule,
    *,
    rebalance_every: int,
    tranches: int,
    anchor_day: int = 17_532,  # 2018-01-01, so tranche schedules are stable across runs
) -> FloatArray:
    """The combined target the tranched strategy holds after the last close in the panel."""
    universe = PointInTimeUniverse(panel, rule)
    t = len(panel) - 1
    offset = max(1, rebalance_every // tranches)
    total = np.zeros(len(panel.symbols))
    for j in range(tranches):
        since = int(panel.days[t]) - anchor_day - j * offset
        last_decision = t - (since % rebalance_every)
        w = strategy.weights(MarketView(panel, max(0, last_decision), universe))
        total += np.zeros(len(panel.symbols)) if w is None else w
    return total / tranches


def record(
    panel: Panel, weights: FloatArray, strategy_name: str, ledger: Path = DEFAULT_LEDGER
) -> PaperRecord:
    date = panel.date_at(len(panel) - 1).isoformat()
    for existing in read(ledger):
        if existing.data_date == date:
            raise ValueError(
                f"a record for {date} already exists in {ledger}; records are append-only"
            )
    held = np.nonzero(weights > 1e-6)[0]
    entry = PaperRecord(
        data_date=date,
        strategy=strategy_name,
        weights={panel.symbols[i]: round(float(weights[i]), 6) for i in held},
        closes={panel.symbols[i]: float(panel.close[-1, i]) for i in held},
    )
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_as_dict(entry)) + "\n")
    return entry


def _as_dict(r: PaperRecord) -> dict[str, object]:
    return {
        "data_date": r.data_date,
        "strategy": r.strategy,
        "weights": r.weights,
        "closes": r.closes,
    }


def read(ledger: Path = DEFAULT_LEDGER) -> list[PaperRecord]:
    if not ledger.exists():
        return []
    out: list[PaperRecord] = []
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            out.append(PaperRecord(d["data_date"], d["strategy"], d["weights"], d["closes"]))
    return out


class RecordedWeights:
    """Replays recorded targets on their dates; holds in between."""

    def __init__(self, panel: Panel, records: list[PaperRecord]) -> None:
        self._by_day: dict[int, FloatArray] = {}
        for r in records:
            from datetime import date

            t = panel.index_of(date.fromisoformat(r.data_date))
            w = np.zeros(len(panel.symbols))
            for sym, weight in r.weights.items():
                if sym in panel.symbols:
                    w[panel.column(sym)] = weight
            self._by_day[t] = w

    @property
    def name(self) -> str:
        return "paper portfolio"

    def weights(self, view: MarketView) -> FloatArray | None:
        return self._by_day.get(view.cursor)


def replay(
    panel: Panel,
    records: list[PaperRecord],
    costs: Costs = BINANCE_SPOT,
    capital: float = 10_000.0,
    no_trade_band: float = 0.0,
) -> RunResult | None:
    """Engine run from the first record to the last close, trading to each recorded target."""
    if not records:
        return None
    from datetime import date

    start = panel.index_of(date.fromisoformat(records[0].data_date))
    return run(
        panel,
        RecordedWeights(panel, records),
        costs,
        RunConfig(
            initial_capital=capital, rebalance_every=1, start=start, no_trade_band=no_trade_band
        ),
    )

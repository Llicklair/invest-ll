"""Aligned price arrays for many assets: one row per day, one column per instrument.

Two data hazards are handled here because every later step depends on them:

- **Ticker reuse.** Binance reused `LUNAUSDT` for a new coin two weeks after the original LUNA
  collapsed. Joined naively, the series shows a jump from $0.00005 to $8.87, a fake 177,000x
  gain. Any gap longer than `MAX_GAP_DAYS` splits a symbol into separate instruments
  (`LUNAUSDT`, then `LUNAUSDT~2`), so the first one ends where the real coin died.
- **Missing days.** A cell is NaN when the instrument did not trade that day. The engine treats an
  instrument whose data has ended as delisted and liquidates it at its last close.
"""

# Boundary with pandas (no type stubs in the project), as in data/loader.py.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import numpy as np
from numpy.typing import NDArray

MAX_GAP_DAYS = 7

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]


@dataclass(frozen=True, slots=True)
class Panel:
    """Daily OHLC and quote volume for many instruments on one calendar.

    `days` are UTC day numbers (days since 1970-01-01). Arrays have shape (len(days), len(symbols)).
    """

    days: IntArray
    symbols: tuple[str, ...]
    open: FloatArray
    high: FloatArray
    low: FloatArray
    close: FloatArray
    quote_volume: FloatArray
    bases: tuple[str, ...] = ()
    periods_per_year: int = 365
    first_valid: IntArray = field(init=False, repr=False)
    last_valid: IntArray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        shape = (len(self.days), len(self.symbols))
        for name in ("open", "high", "low", "close", "quote_volume"):
            arr: FloatArray = getattr(self, name)
            if arr.shape != shape:
                raise ValueError(f"{name} has shape {arr.shape}, expected {shape}")
        if len(self.days) > 1 and bool(np.any(np.diff(self.days) <= 0)):
            raise ValueError("days must be strictly increasing")
        valid = ~np.isnan(self.close)
        if len(self.days) == 0:
            first = np.zeros(len(self.symbols), dtype=np.int64)
            last = np.full(len(self.symbols), -1, dtype=np.int64)
        else:
            any_valid = valid.any(axis=0)
            first = np.where(any_valid, valid.argmax(axis=0), len(self.days))
            last = np.where(any_valid, len(self.days) - 1 - valid[::-1].argmax(axis=0), -1)
        object.__setattr__(self, "first_valid", first.astype(np.int64))
        object.__setattr__(self, "last_valid", last.astype(np.int64))
        if not self.bases:
            object.__setattr__(self, "bases", tuple(_base_of(s) for s in self.symbols))

    def __len__(self) -> int:
        return len(self.days)

    def index_of(self, day: date) -> int:
        """Row of the first day on or after `day`."""
        target = (datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp()) // 86_400
        return int(np.searchsorted(self.days, int(target)))

    def date_at(self, row: int) -> date:
        return datetime.fromtimestamp(int(self.days[row]) * 86_400, UTC).date()

    def column(self, symbol: str) -> int:
        return self.symbols.index(symbol)

    def slice_rows(self, start: int, stop: int) -> Panel:
        """A sub-panel on rows [start, stop). Instrument data outside the window is dropped."""
        return Panel(
            days=self.days[start:stop],
            symbols=self.symbols,
            open=self.open[start:stop],
            high=self.high[start:stop],
            low=self.low[start:stop],
            close=self.close[start:stop],
            quote_volume=self.quote_volume[start:stop],
            bases=self.bases,
            periods_per_year=self.periods_per_year,
        )

    def select(self, symbols: Sequence[str]) -> Panel:
        cols = [self.column(s) for s in symbols]
        return Panel(
            days=self.days,
            symbols=tuple(symbols),
            open=self.open[:, cols],
            high=self.high[:, cols],
            low=self.low[:, cols],
            close=self.close[:, cols],
            quote_volume=self.quote_volume[:, cols],
            bases=tuple(self.bases[c] for c in cols),
            periods_per_year=self.periods_per_year,
        )


def _base_of(symbol: str) -> str:
    plain = symbol.split("~")[0]
    return plain.removesuffix("USDT")


def split_segments(days: IntArray, max_gap: int = MAX_GAP_DAYS) -> list[tuple[int, int]]:
    """Index ranges [start, stop) of runs with no gap longer than `max_gap` days."""
    if len(days) == 0:
        return []
    breaks = np.nonzero(np.diff(days) > max_gap)[0] + 1
    starts = [0, *breaks.tolist()]
    stops = [*breaks.tolist(), len(days)]
    return list(zip(starts, stops, strict=True))


def from_long(
    rows: Any,
    *,
    bases: dict[str, str] | None = None,
    max_gap: int = MAX_GAP_DAYS,
    periods_per_year: int = 365,
    contiguous_days: bool = True,
) -> Panel:
    """Build a panel from a long table with columns symbol, day, open, high, low, close, quote_volume.

    `rows` is a pandas DataFrame. With `contiguous_days` (crypto) every calendar day between the
    first and last row gets a row; otherwise only days present in the data do (exchange sessions).
    """
    frame = rows.sort_values(["symbol", "day"])
    all_days = frame["day"].to_numpy(dtype=np.int64)
    if contiguous_days:
        days = np.arange(int(all_days.min()), int(all_days.max()) + 1, dtype=np.int64)
    else:
        days = np.unique(all_days)

    names: list[str] = []
    base_names: list[str] = []
    columns: dict[str, list[FloatArray]] = {k: [] for k in ("open", "high", "low", "close", "qv")}
    for symbol, group in frame.groupby("symbol", sort=True):
        sym = str(symbol)
        g_days = group["day"].to_numpy(dtype=np.int64)
        values = {
            "open": group["open"].to_numpy(dtype=np.float64),
            "high": group["high"].to_numpy(dtype=np.float64),
            "low": group["low"].to_numpy(dtype=np.float64),
            "close": group["close"].to_numpy(dtype=np.float64),
            "qv": group["quote_volume"].to_numpy(dtype=np.float64),
        }
        for n, (a, b) in enumerate(split_segments(g_days, max_gap), start=1):
            names.append(sym if n == 1 else f"{sym}~{n}")
            base_names.append((bases or {}).get(sym, _base_of(sym)))
            rows_idx = np.searchsorted(days, g_days[a:b])
            for key, arr in values.items():
                col = np.full(len(days), np.nan)
                col[rows_idx] = arr[a:b]
                columns[key].append(col)

    def stack(key: str) -> FloatArray:
        if not columns[key]:
            return np.empty((len(days), 0))
        return np.column_stack(columns[key]).astype(np.float64)

    return Panel(
        days=days,
        symbols=tuple(names),
        open=stack("open"),
        high=stack("high"),
        low=stack("low"),
        close=stack("close"),
        quote_volume=stack("qv"),
        bases=tuple(base_names),
        periods_per_year=periods_per_year,
    )


def load_binance_universe(path: Any) -> Panel:
    """Panel from the parquet written by `invest_ll.fetch.binance_universe` (read from disk only)."""
    import json
    from pathlib import Path

    import pandas as pd

    p = Path(path)
    klines = p / "klines_1d.parquet" if p.is_dir() else p
    frame = pd.read_parquet(klines)
    manifest_path = klines.parent / "manifest.json"
    bases: dict[str, str] | None = None
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        bases = {s["symbol"]: s["base"] for s in manifest["symbols"]}
    return from_long(frame, bases=bases)

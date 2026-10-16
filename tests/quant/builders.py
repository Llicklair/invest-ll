"""Small synthetic panels with predictable outcomes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

from invest_ll.quant.panel import Panel

# 2024-01-01 as a UTC day number.
DAY0 = 19_723


def panel_from_closes(
    closes: Mapping[str, Sequence[float | None]],
    *,
    opens: Mapping[str, Sequence[float | None]] | None = None,
    volume: float = 5_000_000.0,
    start_day: int = DAY0,
) -> Panel:
    """One column per symbol; None means "did not trade that day". Opens default to the closes."""
    symbols = tuple(closes)
    length = max(len(v) for v in closes.values())

    def matrix(source: Mapping[str, Sequence[float | None]]) -> np.ndarray:
        out = np.full((length, len(symbols)), np.nan)
        for j, s in enumerate(symbols):
            for i, v in enumerate(source[s]):
                if v is not None:
                    out[i, j] = float(v)
        return out

    c = matrix(closes)
    o = matrix(opens) if opens is not None else c.copy()
    qv = np.where(np.isnan(c), np.nan, volume)
    return Panel(
        days=np.arange(start_day, start_day + length, dtype=np.int64),
        symbols=symbols,
        open=o,
        high=np.fmax(o, c),
        low=np.fmin(o, c),
        close=c,
        quote_volume=qv,
    )


def random_walk_panel(n_assets: int, n_days: int, seed: int = 1) -> Panel:
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0005, 0.03, size=(n_days, n_assets))
    closes = 100 * np.cumprod(1 + rets, axis=0)
    opens = closes * (1 + rng.normal(0, 0.002, size=closes.shape))
    return Panel(
        days=np.arange(DAY0, DAY0 + n_days, dtype=np.int64),
        symbols=tuple(f"C{i}USDT" for i in range(n_assets)),
        open=opens,
        high=np.fmax(opens, closes) * 1.01,
        low=np.fmin(opens, closes) * 0.99,
        close=closes,
        quote_volume=rng.uniform(1e6, 5e7, size=closes.shape),
    )

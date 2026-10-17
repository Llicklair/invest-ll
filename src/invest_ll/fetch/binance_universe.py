"""Download daily candles for every Binance spot USDT pair, delisted ones included.

Why this exists: a backtest on today's survivors is the most convincing lie a backtest can tell.
`docs/horizontes.md` measured a crypto rotation on BTC, ETH, SOL and BNB, a list picked in 2026
when those four were already known winners. To build a universe that only uses what was known on
each date, we need the coins that later died too (LUNA, FTT, UST, SRM...). Binance still serves the
full history of its delisted pairs (status `BREAK` in `exchangeInfo`), so the reference data can be
complete without paid vendors.

Output (under `data/market/binance-universe/`, ignored by git):
- `klines_1d.parquet`: one row per (symbol, UTC day) with OHLC, base volume, quote volume, trades.
- `manifest.json`: every symbol with its status and base asset, plus when it was downloaded. This is
  the provenance record: a backtest run today can be reproduced from the same files later.

Only public endpoints are used; there are no credentials anywhere in this module.
"""

# Boundary with an untyped library (ccxt), same relaxation as fetch/providers/crypto.py.
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false, reportMissingTypeStubs=false
# pyright: reportAttributeAccessIssue=false, reportUnknownParameterType=false

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, Protocol

from invest_ll.fetch.atomic_write import replace_atomically

DEFAULT_ROOT = Path("data/market/binance-universe")
KLINES_FILE = "klines_1d.parquet"
MANIFEST_FILE = "manifest.json"
QUOTE = "USDT"
DAY_MS = 86_400_000
PAGE = 1000
# Binance spot opened in July 2017; nothing older exists.
EPOCH_MS = int(datetime(2017, 7, 1, tzinfo=UTC).timestamp() * 1000)

COLUMNS = ("symbol", "day", "open", "high", "low", "close", "volume", "quote_volume", "trades")


@dataclass(frozen=True, slots=True)
class SymbolInfo:
    symbol: str
    base: str
    status: str


class KlineClient(Protocol):
    """The two Binance calls this module needs. ccxt's binance client satisfies it."""

    def publicGetExchangeInfo(self) -> dict[str, Any]: ...  # noqa: N802 - Binance's own name

    def publicGetKlines(self, params: dict[str, Any]) -> list[list[Any]]: ...  # noqa: N802


def list_symbols(client: KlineClient) -> list[SymbolInfo]:
    """Every spot pair quoted in USDT, trading or delisted."""
    info = client.publicGetExchangeInfo()
    return sorted(
        (
            SymbolInfo(symbol=s["symbol"], base=s["baseAsset"], status=s["status"])
            for s in info["symbols"]
            if s.get("quoteAsset") == QUOTE
        ),
        key=lambda s: s.symbol,
    )


def fetch_daily(
    client: KlineClient, symbol: str, *, since_ms: int, until_ms: int
) -> list[tuple[Any, ...]]:
    """All closed daily candles of one symbol in [since_ms, until_ms), oldest first."""
    rows: list[tuple[Any, ...]] = []
    start = since_ms
    while start < until_ms:
        batch = client.publicGetKlines(
            {"symbol": symbol, "interval": "1d", "startTime": start, "limit": PAGE}
        )
        if not batch:
            break
        for k in batch:
            open_ms = int(k[0])
            if open_ms >= until_ms:
                break
            rows.append(
                (
                    symbol,
                    open_ms // DAY_MS,
                    float(k[1]),
                    float(k[2]),
                    float(k[3]),
                    float(k[4]),
                    float(k[5]),
                    float(k[7]),
                    int(k[8]),
                )
            )
        last_open = int(batch[-1][0])
        if len(batch) < PAGE or last_open + DAY_MS >= until_ms:
            break
        start = last_open + DAY_MS
    return rows


def download(
    client: KlineClient,
    root: Path = DEFAULT_ROOT,
    *,
    now: datetime | None = None,
    symbols: Iterable[str] | None = None,
    progress: Callable[[int, int, str], None] | None = None,
    checkpoint_every: int = 100,
) -> Path:
    """Download (or extend) the universe on disk and return the klines file path.

    Incremental: symbols already on disk are only fetched from their last stored day onward. The
    current UTC day is excluded because its candle is still open.
    """
    import pandas as pd

    moment = now or datetime.now(UTC)
    today_ms = int(datetime(moment.year, moment.month, moment.day, tzinfo=UTC).timestamp() * 1000)
    infos = list_symbols(client)
    wanted = set(symbols) if symbols is not None else None
    if wanted is not None:
        infos = [i for i in infos if i.symbol in wanted]

    root.mkdir(parents=True, exist_ok=True)
    path = root / KLINES_FILE
    existing = pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=list(COLUMNS))
    last_day: dict[str, int] = (
        existing.groupby("symbol")["day"].max().astype(int).to_dict() if len(existing) else {}
    )

    merged = existing
    fresh: list[tuple[Any, ...]] = []
    for n, info in enumerate(infos, start=1):
        since = (last_day[info.symbol] + 1) * DAY_MS if info.symbol in last_day else EPOCH_MS
        if since < today_ms:
            fresh.extend(fetch_daily(client, info.symbol, since_ms=since, until_ms=today_ms))
        if progress is not None:
            progress(n, len(infos), info.symbol)
        # Checkpoint: a failure halfway through must not throw away what was already downloaded.
        if n % checkpoint_every == 0 or n == len(infos):
            merged = _merge(merged, fresh)
            # In one step: the panel may be reading this file while it updates in the background.
            replace_atomically(path, partial(merged.to_parquet, index=False))
            fresh = []

    _write_manifest(root, infos, merged, moment)
    return path


def _merge(existing: Any, rows: list[tuple[Any, ...]]) -> Any:
    import pandas as pd

    added = pd.DataFrame(rows, columns=list(COLUMNS))
    frames = [f for f in (existing, added) if len(f)]
    merged = pd.concat(frames, ignore_index=True) if frames else added
    return merged.drop_duplicates(subset=["symbol", "day"], keep="last").sort_values(
        ["symbol", "day"], ignore_index=True
    )


def _write_manifest(root: Path, infos: Sequence[SymbolInfo], frame: Any, moment: datetime) -> None:
    spans = frame.groupby("symbol")["day"].agg(["min", "max", "count"]).to_dict("index")
    entries: list[dict[str, Any]] = []
    for info in infos:
        span = spans.get(info.symbol)
        entry: dict[str, Any] = asdict(info)
        if span is not None:
            entry["first_day"] = _iso(int(span["min"]))
            entry["last_day"] = _iso(int(span["max"]))
            entry["bars"] = int(span["count"])
        entries.append(entry)
    manifest = {
        "source": "Binance spot public API (api.binance.com /api/v3/klines, interval 1d)",
        "quote": QUOTE,
        "downloaded_at": moment.isoformat(),
        "symbols": entries,
    }
    (root / MANIFEST_FILE).write_text(json.dumps(manifest, indent=1), encoding="utf-8")


def _iso(day: int) -> str:
    return datetime.fromtimestamp(day * 86_400, UTC).date().isoformat()


def default_client() -> KlineClient:
    """ccxt's Binance client with its own rate limiting (public endpoints only)."""
    import ccxt

    client: KlineClient = ccxt.binance({"enableRateLimit": True})  # pyright: ignore[reportAssignmentType]
    return client

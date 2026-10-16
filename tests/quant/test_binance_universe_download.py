"""The universe downloader, against a fake Binance client (the suite runs without network)."""

# Boundary with pandas (no type stubs in the project), as in data/loader.py.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from invest_ll.fetch.binance_universe import DAY_MS, download

NOW = datetime(2024, 1, 20, 15, 0, tzinfo=UTC)
DAY0 = int(datetime(2024, 1, 1, tzinfo=UTC).timestamp() * 1000)


class FakeBinance:
    def __init__(self, days: dict[str, int]) -> None:
        self.days = days
        self.calls: list[dict[str, Any]] = []

    def publicGetExchangeInfo(self) -> dict[str, Any]:  # noqa: N802
        return {
            "symbols": [
                {
                    "symbol": "AAAUSDT",
                    "baseAsset": "AAA",
                    "quoteAsset": "USDT",
                    "status": "TRADING",
                },
                {
                    "symbol": "DEADUSDT",
                    "baseAsset": "DEAD",
                    "quoteAsset": "USDT",
                    "status": "BREAK",
                },
                {"symbol": "AAABTC", "baseAsset": "AAA", "quoteAsset": "BTC", "status": "TRADING"},
            ]
        }

    def publicGetKlines(self, params: dict[str, Any]) -> list[list[Any]]:  # noqa: N802
        self.calls.append(params)
        n = self.days[params["symbol"]]
        opens = [DAY0 + i * DAY_MS for i in range(n)]
        rows = [o for o in opens if o >= params["startTime"]][: params["limit"]]
        return [[o, "1", "2", "0.5", "1.5", "10", o + DAY_MS - 1, "15", 7] for o in rows]


def test_downloads_trading_and_delisted_usdt_pairs_and_skips_the_open_day(tmp_path: Path) -> None:
    client = FakeBinance({"AAAUSDT": 30, "DEADUSDT": 5})
    path = download(client, tmp_path, now=NOW)

    frame = pd.read_parquet(path)
    assert set(frame["symbol"]) == {"AAAUSDT", "DEADUSDT"}
    # 2024-01-20 is still open at NOW: only 19 closed days of AAA.
    assert (frame["symbol"] == "AAAUSDT").sum() == 19
    assert (frame["symbol"] == "DEADUSDT").sum() == 5
    assert frame["quote_volume"].iloc[0] == 15.0

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    statuses = {s["symbol"]: s["status"] for s in manifest["symbols"]}
    assert statuses == {"AAAUSDT": "TRADING", "DEADUSDT": "BREAK"}


def test_a_second_run_only_fetches_new_days(tmp_path: Path) -> None:
    client = FakeBinance({"AAAUSDT": 30, "DEADUSDT": 5})
    download(client, tmp_path, now=NOW)
    client.calls.clear()
    later = datetime(2024, 1, 25, 1, 0, tzinfo=UTC)
    path = download(client, tmp_path, now=later)

    starts = {c["symbol"]: c["startTime"] for c in client.calls}
    assert starts["AAAUSDT"] == DAY0 + 19 * DAY_MS
    frame = pd.read_parquet(path)
    assert (frame["symbol"] == "AAAUSDT").sum() == 24
    assert not frame.duplicated(["symbol", "day"]).any()

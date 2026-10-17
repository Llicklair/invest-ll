"""Daily history of the asset-class ETFs used by the equity study, from Yahoo Finance.

Prices are split- and dividend-adjusted (`auto_adjust=True`), so the series measure total return.
The current session is dropped when it may still be open. US-listed ETFs stand in for the UCITS
versions a European investor would buy; the asset classes and their history are the same.
"""

# Boundary with untyped libraries (yfinance, pandas), as in fetch/providers/equity.py.
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false, reportMissingTypeStubs=false

from __future__ import annotations

from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from invest_ll.fetch.atomic_write import replace_atomically

DEFAULT_ROOT = Path("data/market/etf-universe")
FILE = "etf_1d.parquet"
TICKERS = ("SPY", "EFA", "EEM", "IEF", "TLT", "GLD", "DBC", "VNQ", "SHY")


def download(root: Path = DEFAULT_ROOT, tickers: tuple[str, ...] = TICKERS) -> Path:
    import pandas as pd
    import yfinance as yf

    epoch = pd.Timestamp("1970-01-01", tz="UTC")
    today = (pd.Timestamp(datetime.now(UTC).date(), tz="UTC") - epoch).days
    frames = []
    for ticker in tickers:
        history = yf.Ticker(ticker).history(start="2004-01-01", auto_adjust=True).reset_index()
        day = (pd.to_datetime(history["Date"], utc=True).dt.normalize() - epoch).dt.days
        frame = pd.DataFrame(
            {
                "symbol": ticker,
                "day": day.astype("int64"),
                "open": history["Open"],
                "high": history["High"],
                "low": history["Low"],
                "close": history["Close"],
                "quote_volume": history["Volume"] * history["Close"],
            }
        )
        frames.append(frame[frame["day"] < today])
    root.mkdir(parents=True, exist_ok=True)
    path = root / FILE
    # In one step: the panel may be reading this file while it updates in the background.
    replace_atomically(path, partial(pd.concat(frames, ignore_index=True).to_parquet, index=False))
    return path

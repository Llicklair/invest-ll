"""Which instruments were investable on a given day, using only what was known that day.

The rule is the one large funds use for a tradable universe: liquidity. On day `t`, rank every
instrument by its median daily quote volume over the previous `window` days and keep the top `n`.
No market capitalisation (not in the data, and survivor-biased when bought from a vendor), no
hand-picked list. Coins that later died are in the ranking while they were liquid, exactly as they
were in front of a real investor.

Some instruments are never eligible because they are not a bet on a crypto asset: stablecoins and
fiat (USDC, FDUSD, EUR...), leveraged tokens (BTCUP, ETHDOWN...), wrapped or pegged copies of
another asset (WBTC, WBETH...) and tokenised gold (PAXG).
"""

from __future__ import annotations

import warnings
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np

from invest_ll.quant.panel import FloatArray, Panel

STABLE_OR_FIAT = frozenset(
    {
        "USDC", "BUSD", "TUSD", "PAX", "USDP", "USDS", "USDSB", "USDSOLD", "DAI", "FDUSD", "UST",
        "USTC", "SUSD", "GUSD", "HUSD", "USDD", "PYUSD", "USDE", "USD1", "RLUSD", "XUSD", "BFUSD",
        "AEUR", "EURI", "EUR", "GBP", "AUD", "TRY", "BRL", "RUB", "ZAR", "UAH", "NGN", "IDRT",
        "BIDR", "BVND", "BKRW", "VAI", "FRAX", "LUSD", "TUSDB", "USDT", "ERD_OLD", "U",
    }
)  # fmt: skip
WRAPPED_OR_PEGGED = frozenset(
    {"WBTC", "WBETH", "BETH", "BNSOL", "CBETH", "RETH", "STETH", "PAXG", "XAUT"}
)
LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")


def exclusion_reason(base: str, known_bases: Iterable[str]) -> str | None:
    """Why an asset can never be in the universe, or None if it can."""
    if base in STABLE_OR_FIAT:
        return "stablecoin or fiat"
    if base in WRAPPED_OR_PEGGED:
        return "wrapped or pegged copy"
    bases = set(known_bases)
    for suffix in LEVERAGED_SUFFIXES:
        stem = base.removesuffix(suffix)
        # BTCUP is a leveraged token on BTC; JUP is a coin. The stem must be a real asset.
        if stem != base and len(stem) >= 3 and stem in bases:
            return "leveraged token"
    return None


@dataclass(frozen=True, slots=True)
class UniverseRule:
    """Point-in-time liquidity universe.

    - `top_n`: how many instruments make the cut each day.
    - `window`: days of history used for the median quote volume.
    - `min_history`: days an instrument must have traded before it can enter. Fresh listings are
      wildly volatile and their first weeks are exactly what a real investor could not have known.
    - `min_quote_volume`: floor on median daily quote volume (USDT), so a thin market never fills a
      slot just because few instruments existed that year.
    """

    top_n: int
    window: int = 30
    min_history: int = 60
    min_quote_volume: float = 1_000_000.0

    def __post_init__(self) -> None:
        if self.top_n < 1 or self.window < 2 or self.min_history < 1:
            raise ValueError("top_n >= 1, window >= 2 and min_history >= 1 are required")


class PointInTimeUniverse:
    """Membership mask per day, computed with data up to and including that day only."""

    __slots__ = ("_allowed", "_cache", "_panel", "_rule")

    def __init__(self, panel: Panel, rule: UniverseRule) -> None:
        self._panel = panel
        self._rule = rule
        bases = set(panel.bases)
        self._allowed = np.array(
            [exclusion_reason(b, bases) is None for b in panel.bases], dtype=bool
        )
        self._cache: dict[int, FloatArray] = {}

    @property
    def rule(self) -> UniverseRule:
        return self._rule

    def liquidity(self, t: int) -> FloatArray:
        """Median quote volume over the last `window` days up to day t (NaN if not enough data)."""
        if t in self._cache:
            return self._cache[t]
        w = self._rule.window
        lo = max(0, t - w + 1)
        block = self._panel.quote_volume[lo : t + 1]
        enough = np.sum(~np.isnan(block), axis=0) >= int(0.8 * w)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN columns: not listed yet
            med = np.nanmedian(block, axis=0)
        out = np.where(enough, med, np.nan)
        self._cache[t] = out
        return out

    def members(self, t: int) -> np.ndarray:
        """Boolean mask of instruments in the universe at the close of day t."""
        panel = self._panel
        traded_today = ~np.isnan(panel.close[t])
        seasoned = (t - panel.first_valid) >= self._rule.min_history
        liq = self.liquidity(t)
        eligible = (
            self._allowed
            & traded_today
            & seasoned
            & ~np.isnan(liq)
            & (np.nan_to_num(liq, nan=0.0) >= self._rule.min_quote_volume)
        )
        if not eligible.any():
            return eligible
        ranked = np.where(eligible, liq, -np.inf)
        k = min(self._rule.top_n, int(eligible.sum()))
        top = np.argpartition(-ranked, k - 1)[:k]
        mask = np.zeros(len(eligible), dtype=bool)
        mask[top] = True
        return mask & eligible

"""
APEX Trading Bot — Correlation Map & Coefficient Engine
========================================================
Defines static directional relationships between all traded instruments
and provides rolling Pearson correlation from DuckDB OHLCV history.

Two layers:
  1. STATIC_CORRELATIONS  — hardcoded directional relationships (always valid)
  2. DynamicCorrelationEngine — rolling 90-day Pearson from stored OHLCV data

Usage:
    from core.correlations import STATIC_CORRELATIONS, DynamicCorrelationEngine
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import pandas as pd
import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
#  STATIC CORRELATION MAP
#  Each entry defines how other instruments relate to the key instrument.
#
#  positive : assets that move in the SAME direction
#  negative : assets that move in the OPPOSITE direction
#  leading  : assets whose moves PRECEDE the key instrument (15–60 min lag)
#  lagging  : assets that FOLLOW the key instrument
#  group    : correlation group name (for position sizing caps)
# ─────────────────────────────────────────────────────────────────────────────

STATIC_CORRELATIONS: dict[str, dict] = {

    # ── GOLD ─────────────────────────────────────────────────────────────────
    "XAUUSD": {
        "positive": ["XAGUSD", "EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"],
        "negative": ["DXY", "US10Y", "USDCHF", "USDJPY", "USDCAD"],
        "leading":  ["DXY", "US10Y", "EURUSD"],
        "lagging":  ["XAGUSD", "XPTUSD"],
        "group":    "safe_haven",
        "description": "Anti-USD, anti-yield safe haven. Falls when USD/yields rise.",
    },

    # ── SILVER ───────────────────────────────────────────────────────────────
    "XAGUSD": {
        "positive": ["XAUUSD", "EURUSD", "copper futures", "AUDUSD"],
        "negative": ["DXY", "US10Y", "USDCHF"],
        "leading":  ["XAUUSD", "DXY"],
        "lagging":  [],
        "group":    "safe_haven",
        "description": "Follows Gold but with higher beta. Also industrial demand driver.",
    },

    # ── EUR/USD ───────────────────────────────────────────────────────────────
    "EURUSD": {
        "positive": ["GBPUSD", "AUDUSD", "NZDUSD", "XAUUSD"],
        "negative": ["DXY", "USDCHF", "USDJPY", "USDCAD"],
        "leading":  ["DXY", "ECB rate differential"],
        "lagging":  ["GBPUSD"],
        "group":    "usd_pairs",
        "description": "Primary anti-DXY pair. Leads most other EUR crosses.",
    },

    # ── GBP/USD ───────────────────────────────────────────────────────────────
    "GBPUSD": {
        "positive": ["EURUSD", "AUDUSD", "XAUUSD"],
        "negative": ["DXY", "USDCHF", "USDJPY"],
        "leading":  ["EURUSD", "DXY"],
        "lagging":  ["EURUSD"],
        "group":    "usd_pairs",
        "description": "Follows EURUSD closely. Higher volatility / wider spreads.",
    },

    # ── AUD/USD ───────────────────────────────────────────────────────────────
    "AUDUSD": {
        "positive": ["EURUSD", "GBPUSD", "NZDUSD", "XAUUSD", "copper"],
        "negative": ["DXY", "USDJPY", "USDCHF"],
        "leading":  ["Iron ore price", "China PMI", "S&P500"],
        "lagging":  ["EURUSD"],
        "group":    "usd_pairs",
        "description": "Commodity / risk-on currency. Tracks China growth and metals.",
    },

    # ── USD/JPY ───────────────────────────────────────────────────────────────
    "USDJPY": {
        "positive": ["DXY", "US10Y", "USDCHF", "S&P500 (risk-on)"],
        "negative": ["XAUUSD", "EURUSD", "GBPUSD"],
        "leading":  ["US10Y", "DXY"],
        "lagging":  [],
        "group":    "usd_pairs",
        "description": "Yield-driven pair. Rises when US yields rise. JPY is safe-haven.",
    },

    # ── USD/CHF ───────────────────────────────────────────────────────────────
    "USDCHF": {
        "positive": ["DXY", "USDJPY"],
        "negative": ["EURUSD", "XAUUSD", "GBPUSD"],
        "leading":  ["DXY", "EURUSD (inverse)"],
        "lagging":  [],
        "group":    "usd_pairs",
        "description": "Mirror of EURUSD (~0.85 inverse correlation). CHF is safe haven.",
    },

    # ── USD/CAD ───────────────────────────────────────────────────────────────
    "USDCAD": {
        "positive": ["DXY"],
        "negative": ["USOIL", "EURUSD", "XAUUSD"],
        "leading":  ["USOIL", "DXY"],
        "lagging":  [],
        "group":    "usd_pairs",
        "description": "Oil-linked pair. CAD strengthens when crude rises.",
    },

    # ── US OIL (WTI) ──────────────────────────────────────────────────────────
    "USOIL": {
        "positive": ["UKCRUOIL", "NATGAS", "CADUSD", "S&P500 (energy sector)"],
        "negative": ["DXY", "USDCAD"],
        "leading":  ["DXY", "S&P500 futures", "EIA inventory"],
        "lagging":  ["energy stocks", "NATGAS"],
        "group":    "energy",
        "description": "Priced in USD — falls when DXY rises. Tracks risk sentiment.",
    },

    # ── UK BRENT CRUDE ────────────────────────────────────────────────────────
    "UKCRUOIL": {
        "positive": ["USOIL", "NATGAS"],
        "negative": ["DXY"],
        "leading":  ["USOIL", "DXY"],
        "lagging":  ["USOIL"],
        "group":    "energy",
        "description": "Typically trades $2-5 premium to WTI. Nearly identical signals.",
    },

    # ── BITCOIN ───────────────────────────────────────────────────────────────
    "BTCUSD": {
        "positive": ["ETHUSD", "SOLUSD", "S&P500", "NASDAQ (risk-on)"],
        "negative": ["DXY", "VIX spikes", "USDJPY (risk-off)"],
        "leading":  ["S&P500 futures (pre-market)", "ETHUSD funding rates"],
        "lagging":  ["ETHUSD"],
        "group":    "crypto",
        "description": "Risk asset. Correlates with S&P500 during risk-off events.",
    },

    # ── ETHEREUM ──────────────────────────────────────────────────────────────
    "ETHUSD": {
        "positive": ["BTCUSD", "SOLUSD", "NASDAQ"],
        "negative": ["DXY", "VIX"],
        "leading":  ["BTCUSD"],
        "lagging":  ["BTCUSD"],
        "group":    "crypto",
        "description": "Follows BTC but with higher beta. ETH/BTC ratio is key signal.",
    },

    # ── S&P 500 ───────────────────────────────────────────────────────────────
    "SPX500": {
        "positive": ["NASDAQ100", "BTCUSD", "AUDUSD", "USOIL", "EURUSD"],
        "negative": ["VIX", "XAUUSD (risk-off)", "USDJPY (safe haven)"],
        "leading":  ["VIX", "S&P500 futures (pre-market)", "US10Y direction"],
        "lagging":  ["sector ETFs"],
        "group":    "risk_asset",
        "description": "Broad risk-on indicator. VIX is its leading fear gauge.",
    },

    # ── NASDAQ 100 ────────────────────────────────────────────────────────────
    "NAS100": {
        "positive": ["SPX500", "BTCUSD", "ETHUSD"],
        "negative": ["US10Y (rate sensitive)", "DXY (earnings impact)", "VIX"],
        "leading":  ["US10Y", "S&P500 futures", "major tech earnings"],
        "lagging":  ["SPX500"],
        "group":    "risk_asset",
        "description": "Tech-heavy. More sensitive to rate rises than SPX500.",
    },

    # ── DXY (USD Index) — reference asset ────────────────────────────────────
    "DXY": {
        "positive": ["USDJPY", "USDCHF", "USDCAD", "US10Y"],
        "negative": ["EURUSD", "GBPUSD", "AUDUSD", "XAUUSD", "USOIL"],
        "leading":  ["Fed rate expectations", "US10Y"],
        "lagging":  [],
        "group":    "macro_reference",
        "description": "Primary USD strength index. Leads most USD pairs and Gold.",
    },

    # ── US 10Y YIELD — reference asset ───────────────────────────────────────
    "US10Y": {
        "positive": ["DXY", "USDJPY", "USDCHF"],
        "negative": ["XAUUSD", "EURUSD", "BTCUSD", "SPX500 (rate sensitive)"],
        "leading":  ["Fed funds futures", "CPI data", "FOMC"],
        "lagging":  [],
        "group":    "macro_reference",
        "description": "Primary rate indicator. Rising yields are bearish for Gold.",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
#  CORRELATION GROUPS
#  Used by risk_manager to enforce position concentration limits.
#  group → list of member symbols
# ─────────────────────────────────────────────────────────────────────────────

CORRELATION_GROUPS: dict[str, list[str]] = {
    "usd_pairs":       ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDJPY", "USDCHF", "USDCAD"],
    "safe_haven":      ["XAUUSD", "XAGUSD", "USDCHF", "USDJPY"],
    "energy":          ["USOIL", "UKCRUOIL", "NATGAS"],
    "crypto":          ["BTCUSD", "ETHUSD", "SOLUSD"],
    "risk_asset":      ["SPX500", "NAS100", "BTCUSD", "USOIL"],
    "macro_reference": ["DXY", "US10Y"],
}

# Max same-direction positions allowed per group
GROUP_MAX_SAME_DIRECTION: dict[str, int] = {
    "usd_pairs":       2,
    "safe_haven":      2,
    "energy":          2,
    "crypto":          1,
    "risk_asset":      2,
    "macro_reference": 0,  # reference only — not traded directly
}


def get_group(symbol: str) -> Optional[str]:
    """Return the correlation group name for a symbol."""
    for group, members in CORRELATION_GROUPS.items():
        if symbol in members:
            return group
    return None


def get_group_max(symbol: str) -> int:
    """Return the max same-direction positions allowed in a symbol's group."""
    group = get_group(symbol)
    if group is None:
        return 2  # default
    return GROUP_MAX_SAME_DIRECTION.get(group, 2)


# ─────────────────────────────────────────────────────────────────────────────
#  DYNAMIC CORRELATION ENGINE
#  Calculates rolling Pearson correlation from DuckDB OHLCV history.
#  Results are cached and refreshed weekly.
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CorrelationResult:
    symbol_a:    str
    symbol_b:    str
    coefficient: float        # -1.0 to +1.0
    n_periods:   int          # number of bars used
    timeframe:   str
    is_reliable: bool         # True if n_periods >= 60
    relationship: str = ""    # "STRONG_POSITIVE" | "POSITIVE" | "NEUTRAL" | "NEGATIVE" | "STRONG_NEGATIVE"

    def __post_init__(self):
        c = self.coefficient
        if   c >= 0.70:  self.relationship = "STRONG_POSITIVE"
        elif c >= 0.40:  self.relationship = "POSITIVE"
        elif c <= -0.70: self.relationship = "STRONG_NEGATIVE"
        elif c <= -0.40: self.relationship = "NEGATIVE"
        else:            self.relationship = "NEUTRAL"


class DynamicCorrelationEngine:
    """
    Calculates rolling Pearson correlation coefficients between instruments
    using OHLCV close prices from DuckDB.

    Coefficients are cached for `cache_hours` hours to avoid repeated
    DuckDB queries on every cycle.
    """

    def __init__(self, db_path: str = "./data/apex.db", cache_hours: int = 6):
        self.db_path    = db_path
        self.cache_hours = cache_hours
        self._cache: dict[str, tuple[float, CorrelationResult]] = {}  # key → (timestamp, result)

    def _cache_key(self, a: str, b: str, tf: str) -> str:
        return f"{min(a,b)}:{max(a,b)}:{tf}"

    def _load_closes(self, symbol: str, timeframe: str, n: int = 90) -> Optional[pd.Series]:
        """Load last n close prices for a symbol from DuckDB."""
        try:
            import duckdb
            con = duckdb.connect(self.db_path, read_only=True)
            rows = con.execute("""
                SELECT timestamp, close FROM ohlcv
                WHERE symbol = ? AND timeframe = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, [symbol, timeframe, n]).fetchall()
            con.close()

            if len(rows) < 20:
                return None

            df = pd.DataFrame(rows, columns=["ts", "close"])
            df = df.sort_values("ts").set_index("ts")
            return df["close"]

        except Exception:
            return None

    def calculate(
        self,
        symbol_a: str,
        symbol_b: str,
        timeframe: str = "H1",
        n_periods: int = 90,
    ) -> Optional[CorrelationResult]:
        """
        Calculate rolling Pearson correlation between two symbols.
        Returns None if insufficient data.
        """
        import time
        cache_key = self._cache_key(symbol_a, symbol_b, timeframe)

        # Check cache
        if cache_key in self._cache:
            cached_time, cached_result = self._cache[cache_key]
            if time.time() - cached_time < self.cache_hours * 3600:
                return cached_result

        closes_a = self._load_closes(symbol_a, timeframe, n_periods)
        closes_b = self._load_closes(symbol_b, timeframe, n_periods)

        if closes_a is None or closes_b is None:
            return None

        # Align on common timestamps
        combined = pd.DataFrame({"a": closes_a, "b": closes_b}).dropna()
        if len(combined) < 20:
            return None

        # Calculate log returns then correlate
        returns = combined.pct_change().dropna()
        if len(returns) < 20:
            return None

        coeff = returns["a"].corr(returns["b"])
        if pd.isna(coeff):
            return None

        result = CorrelationResult(
            symbol_a=symbol_a,
            symbol_b=symbol_b,
            coefficient=round(float(coeff), 4),
            n_periods=len(returns),
            timeframe=timeframe,
            is_reliable=len(returns) >= 60,
        )

        self._cache[cache_key] = (time.time(), result)
        return result

    def get_all_correlations(
        self,
        symbol: str,
        candidates: list[str],
        timeframe: str = "H1",
    ) -> list[CorrelationResult]:
        """
        Calculate correlation between `symbol` and all candidates.
        Returns sorted by abs(coefficient) descending.
        """
        results = []
        for candidate in candidates:
            if candidate == symbol:
                continue
            r = self.calculate(symbol, candidate, timeframe)
            if r is not None:
                results.append(r)
        return sorted(results, key=lambda r: abs(r.coefficient), reverse=True)

    def get_strongest_correlation(
        self,
        symbol: str,
        candidates: list[str],
        min_abs_coeff: float = 0.50,
        timeframe: str = "H1",
    ) -> Optional[CorrelationResult]:
        """Return the strongest reliable correlation above the threshold."""
        results = self.get_all_correlations(symbol, candidates, timeframe)
        for r in results:
            if r.is_reliable and abs(r.coefficient) >= min_abs_coeff:
                return r
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  DIVERGENCE PAIR DEFINITIONS
#  Used by the correlation agent to detect catch-up opportunities.
#  Format: (leader, lagger, same_direction, threshold_pct, signal_symbol, signal_dir)
# ─────────────────────────────────────────────────────────────────────────────

DIVERGENCE_PAIRS = [
    # Gold leads Silver
    ("XAUUSD",  "XAGUSD",  True,   0.40,  "XAGUSD",  "BUY"),
    ("XAUUSD",  "XAGUSD",  True,  -0.40,  "XAGUSD",  "SELL"),
    # DXY leads Gold (inverse)
    ("DXY",     "XAUUSD",  False,  0.30,  "XAUUSD",  "SELL"),
    ("DXY",     "XAUUSD",  False, -0.30,  "XAUUSD",  "BUY"),
    # EUR leads GBP
    ("EURUSD",  "GBPUSD",  True,   0.25,  "GBPUSD",  "BUY"),
    ("EURUSD",  "GBPUSD",  True,  -0.25,  "GBPUSD",  "SELL"),
    # EUR leads AUD (both anti-USD)
    ("EURUSD",  "AUDUSD",  True,   0.30,  "AUDUSD",  "BUY"),
    ("EURUSD",  "AUDUSD",  True,  -0.30,  "AUDUSD",  "SELL"),
    # BTC leads ETH
    ("BTCUSD",  "ETHUSD",  True,   0.80,  "ETHUSD",  "BUY"),
    ("BTCUSD",  "ETHUSD",  True,  -0.80,  "ETHUSD",  "SELL"),
    # Oil leads CAD (inverse USDCAD)
    ("USOIL",   "USDCAD",  False,  0.50,  "USDCAD",  "SELL"),
    ("USOIL",   "USDCAD",  False, -0.50,  "USDCAD",  "BUY"),
    # S&P leads BTC on risk-off/on
    ("SPX500",  "BTCUSD",  True,   0.60,  "BTCUSD",  "BUY"),
    ("SPX500",  "BTCUSD",  True,  -0.60,  "BTCUSD",  "SELL"),
]

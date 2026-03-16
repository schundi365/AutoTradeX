"""
APEX Bot — Correlation Manager Agent
======================================
Ported from apex_bot/agents/correlation_agent.py and apex_bot/core/correlations.py.

Sits between market_analyst and sentiment_agent in the LangGraph pipeline.

Responsibilities:
  1. Correlation confirmation  — boost/reduce signal score based on aligned assets
  2. Leading indicator check   — flag premature signals before leaders have moved
  3. Divergence detection      — generate catch-up signals when correlated assets diverge
  4. Correlation-adjusted size — scale lot sizes down for correlated open positions
  5. Over-correlation veto     — reject signals when group concentration is too high

Pipeline position:
  market_analyst → [correlation_manager] → sentiment_agent → ...
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import pandas as pd
import numpy as np

from core.models import (
    BotState, TradingSignal, Direction, AssetClass,
    SignalStrength, AgentMessage, Trade,
)
from core.config import settings
from core.logger import get_agent_logger

log = get_agent_logger("CORR")


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
        "group":    "SAFE_HAVENS",
        "description": "Anti-USD, anti-yield safe haven. Falls when USD/yields rise.",
    },

    # ── SILVER ───────────────────────────────────────────────────────────────
    "XAGUSD": {
        "positive": ["XAUUSD", "EURUSD", "AUDUSD"],
        "negative": ["DXY", "US10Y", "USDCHF"],
        "leading":  ["XAUUSD", "DXY"],
        "lagging":  [],
        "group":    "SAFE_HAVENS",
        "description": "Follows Gold but with higher beta. Also industrial demand driver.",
    },

    # ── EUR/USD ───────────────────────────────────────────────────────────────
    "EURUSD": {
        "positive": ["GBPUSD", "AUDUSD", "NZDUSD", "XAUUSD"],
        "negative": ["DXY", "USDCHF", "USDJPY", "USDCAD"],
        "leading":  ["DXY"],
        "lagging":  ["GBPUSD"],
        "group":    "USD_PAIRS",
        "description": "Primary anti-DXY pair. Leads most other EUR crosses.",
    },

    # ── GBP/USD ───────────────────────────────────────────────────────────────
    "GBPUSD": {
        "positive": ["EURUSD", "AUDUSD", "XAUUSD"],
        "negative": ["DXY", "USDCHF", "USDJPY"],
        "leading":  ["EURUSD", "DXY"],
        "lagging":  ["EURUSD"],
        "group":    "USD_PAIRS",
        "description": "Follows EURUSD closely. Higher volatility / wider spreads.",
    },

    # ── AUD/USD ───────────────────────────────────────────────────────────────
    "AUDUSD": {
        "positive": ["EURUSD", "GBPUSD", "NZDUSD", "XAUUSD"],
        "negative": ["DXY", "USDJPY", "USDCHF"],
        "leading":  ["XAUUSD"],
        "lagging":  ["EURUSD"],
        "group":    "USD_PAIRS",
        "description": "Commodity / risk-on currency. Tracks China growth and metals.",
    },

    # ── USD/JPY ───────────────────────────────────────────────────────────────
    "USDJPY": {
        "positive": ["DXY", "US10Y", "USDCHF"],
        "negative": ["XAUUSD", "EURUSD", "GBPUSD"],
        "leading":  ["US10Y", "DXY"],
        "lagging":  [],
        "group":    "USD_PAIRS",
        "description": "Yield-driven pair. Rises when US yields rise. JPY is safe-haven.",
    },

    # ── USD/CHF ───────────────────────────────────────────────────────────────
    "USDCHF": {
        "positive": ["DXY", "USDJPY"],
        "negative": ["EURUSD", "XAUUSD", "GBPUSD"],
        "leading":  ["DXY"],
        "lagging":  [],
        "group":    "USD_PAIRS",
        "description": "Mirror of EURUSD (~0.85 inverse correlation). CHF is safe haven.",
    },

    # ── USD/CAD ───────────────────────────────────────────────────────────────
    "USDCAD": {
        "positive": ["DXY"],
        "negative": ["USOIL", "EURUSD", "XAUUSD"],
        "leading":  ["USOIL", "DXY"],
        "lagging":  [],
        "group":    "USD_PAIRS",
        "description": "Oil-linked pair. CAD strengthens when crude rises.",
    },

    # ── US OIL (WTI) ──────────────────────────────────────────────────────────
    "USOIL": {
        "positive": ["UKOIL", "NATGAS"],
        "negative": ["DXY", "USDCAD"],
        "leading":  ["DXY"],
        "lagging":  ["NATGAS"],
        "group":    "ENERGY",
        "description": "Priced in USD — falls when DXY rises. Tracks risk sentiment.",
    },

    # ── UK BRENT CRUDE ────────────────────────────────────────────────────────
    "UKOIL": {
        "positive": ["USOIL", "NATGAS"],
        "negative": ["DXY"],
        "leading":  ["USOIL", "DXY"],
        "lagging":  ["USOIL"],
        "group":    "ENERGY",
        "description": "Typically trades $2-5 premium to WTI. Nearly identical signals.",
    },

    # ── BITCOIN ───────────────────────────────────────────────────────────────
    "BTC": {
        "positive": ["ETH", "SP500"],
        "negative": ["DXY"],
        "leading":  ["SP500"],
        "lagging":  ["ETH"],
        "group":    "CRYPTO",
        "description": "Risk asset. Correlates with SP500 during risk-off events.",
    },
    "BTCUSD": {
        "positive": ["ETHUSD", "SP500"],
        "negative": ["DXY"],
        "leading":  ["SP500"],
        "lagging":  ["ETHUSD"],
        "group":    "CRYPTO",
        "description": "Risk asset. Correlates with SP500 during risk-off events.",
    },

    # ── ETHEREUM ──────────────────────────────────────────────────────────────
    "ETH": {
        "positive": ["BTC", "SP500"],
        "negative": ["DXY"],
        "leading":  ["BTC"],
        "lagging":  ["BTC"],
        "group":    "CRYPTO",
        "description": "Follows BTC but with higher beta.",
    },
    "ETHUSD": {
        "positive": ["BTCUSD", "SP500"],
        "negative": ["DXY"],
        "leading":  ["BTCUSD"],
        "lagging":  ["BTCUSD"],
        "group":    "CRYPTO",
        "description": "Follows BTC but with higher beta.",
    },

    # ── S&P 500 ───────────────────────────────────────────────────────────────
    "SP500": {
        "positive": ["BTC", "AUDUSD", "USOIL", "EURUSD"],
        "negative": ["XAUUSD", "USDJPY"],
        "leading":  ["XAUUSD"],
        "lagging":  [],
        "group":    "RISK_ASSETS",
        "description": "Broad risk-on indicator.",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
#  CORRELATION GROUPS  (aligned with core/config.py CORRELATION_GROUPS keys)
#  group → (list of member symbols, max_same_direction_positions)
# ─────────────────────────────────────────────────────────────────────────────

CORR_GROUP_MEMBERS: dict[str, list[str]] = {
    "USD_PAIRS":        ["EURUSD", "GBPUSD", "AUDUSD", "USDCHF", "USDCAD", "USDJPY", "NZDUSD"],
    # Only precious metals in the precious-metals group.
    # USDCHF and USDJPY were previously included here but they are in USD_PAIRS —
    # keeping them in SAFE_HAVENS caused valid XAUUSD signals to be blocked whenever
    # USDCHF or USDJPY positions were already open (they move OPPOSITE to gold on
    # USD strength, so counting them as "same group / same direction" was wrong).
    "PRECIOUS_METALS":  ["XAUUSD", "XAGUSD", "XPTUSD"],
    "RISK_ASSETS":      ["SP500", "BTC", "ETH", "USOIL"],
    "CRYPTO":           ["BTC", "ETH", "SOL", "BTCUSD", "ETHUSD"],
    "ENERGY":           ["USOIL", "UKOIL", "NATGAS"],
}

GROUP_MAX_SAME_DIRECTION: dict[str, int] = {
    "USD_PAIRS":       2,
    "PRECIOUS_METALS": 2,   # allow XAUUSD + XAGUSD but not a third metal
    "RISK_ASSETS":     2,
    "CRYPTO":          1,
    "ENERGY":          2,
}


# ─────────────────────────────────────────────────────────────────────────────
#  DIVERGENCE PAIR DEFINITIONS
#  Used to detect catch-up opportunities.
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
    ("BTC",     "ETH",     True,   0.80,  "ETH",     "BUY"),
    ("BTC",     "ETH",     True,  -0.80,  "ETH",     "SELL"),
    # Oil leads CAD (inverse USDCAD)
    ("USOIL",   "USDCAD",  False,  0.50,  "USDCAD",  "SELL"),
    ("USOIL",   "USDCAD",  False, -0.50,  "USDCAD",  "BUY"),
    # SP500 leads BTC on risk-off/on
    ("SP500",   "BTC",     True,   0.60,  "BTC",     "BUY"),
    ("SP500",   "BTC",     True,  -0.60,  "BTC",     "SELL"),
]


# ─────────────────────────────────────────────────────────────────────────────
#  DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CorrelationResult:
    symbol_a:    str
    symbol_b:    str
    coefficient: float        # -1.0 to +1.0
    n_periods:   int
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


@dataclass
class ConfirmationResult:
    boost:          float           # net score adjustment (-2.0 to +2.0)
    confirmations:  int
    contradictions: int
    detail:         list            # human-readable per-asset results


@dataclass
class LeadingResult:
    aligned:  bool
    warnings: list
    confidence_factor: float        # 1.0 = no change, 0.8 = reduce by 20%


@dataclass
class DivergenceSignal:
    symbol:       str
    direction:    str
    score:        float
    confidence:   float
    leader:       str
    leader_change: float
    lagger_change: float
    reasoning:    str


# ─────────────────────────────────────────────────────────────────────────────
#  DYNAMIC CORRELATION ENGINE
#  Calculates rolling Pearson correlation from DuckDB OHLCV history.
# ─────────────────────────────────────────────────────────────────────────────

class DynamicCorrelationEngine:
    """
    Calculates rolling Pearson correlation coefficients between instruments
    using OHLCV close prices from DuckDB. Results are cached for `cache_hours`.
    """

    def __init__(self, cache_hours: int = 6):
        self.db_path     = settings.training.duckdb_path
        self.cache_hours = cache_hours
        self._cache: dict[str, tuple[float, CorrelationResult]] = {}

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
        """Calculate rolling Pearson correlation. Returns None if insufficient data."""
        import time
        cache_key = self._cache_key(symbol_a, symbol_b, timeframe)

        if cache_key in self._cache:
            cached_time, cached_result = self._cache[cache_key]
            if time.time() - cached_time < self.cache_hours * 3600:
                return cached_result

        closes_a = self._load_closes(symbol_a, timeframe, n_periods)
        closes_b = self._load_closes(symbol_b, timeframe, n_periods)
        if closes_a is None or closes_b is None:
            return None

        combined = pd.DataFrame({"a": closes_a, "b": closes_b}).dropna()
        if len(combined) < 20:
            return None

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
        candidates: list,
        timeframe: str = "H1",
    ) -> list:
        results = []
        for candidate in candidates:
            if candidate == symbol:
                continue
            r = self.calculate(symbol, candidate, timeframe)
            if r is not None:
                results.append(r)
        return sorted(results, key=lambda r: abs(r.coefficient), reverse=True)


# Singleton dynamic engine — shared across cycles
_dyn_engine = DynamicCorrelationEngine()


# ─────────────────────────────────────────────────────────────────────────────
#  GROUP HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_group(symbol: str) -> Optional[str]:
    """Return the correlation group name for a symbol."""
    sym = symbol.upper()
    for group, members in CORR_GROUP_MEMBERS.items():
        if any(m in sym or sym in m or sym == m for m in members):
            return group
    return None


def _get_group_max(symbol: str) -> int:
    """Return max same-direction positions allowed for a symbol's group."""
    group = _get_group(symbol)
    if group is None:
        return 2
    return GROUP_MAX_SAME_DIRECTION.get(group, 2)


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS — price momentum from BotState OHLCV cache
# ─────────────────────────────────────────────────────────────────────────────

def _get_session_change_pct(symbol: str, state: BotState) -> Optional[float]:
    """Return approximate session change % for a symbol from OHLCV cache or quotes."""
    bars = state.ohlcv_cache.get(symbol)
    if bars and len(bars) >= 2:
        try:
            recent = bars[-1]
            prev   = bars[-2]
            c_now  = recent.close  if hasattr(recent, "close")  else recent["close"]
            c_prev = prev.close    if hasattr(prev,   "close")  else prev["close"]
            if c_prev and c_prev != 0:
                return (c_now - c_prev) / c_prev * 100
        except Exception:
            pass

    quote = state.quotes.get(symbol)
    if quote:
        mid = (quote.bid + quote.ask) / 2
        yesterday = getattr(quote, "prev_close", None)
        if yesterday and yesterday != 0:
            return (mid - yesterday) / yesterday * 100
    return None


def _get_momentum_direction(symbol: str, state: BotState, bars: int = 5) -> Optional[str]:
    """Return 'BUY' / 'SELL' / None based on short-term rate-of-change."""
    ohlcv = state.ohlcv_cache.get(symbol)
    if not ohlcv or len(ohlcv) < bars + 1:
        return None
    try:
        closes = [
            float(b.close if hasattr(b, "close") else b["close"])
            for b in ohlcv[-(bars + 1):]
        ]
        roc = (closes[-1] - closes[0]) / closes[0] * 100
        if   roc > 0.05:  return "BUY"
        elif roc < -0.05: return "SELL"
        return None
    except Exception:
        return None


def _get_roc(symbol: str, state: BotState, bars: int = 5) -> Optional[float]:
    """Return raw rate-of-change % over last `bars` periods."""
    ohlcv = state.ohlcv_cache.get(symbol)
    if not ohlcv or len(ohlcv) < bars + 1:
        return None
    try:
        closes = [
            float(b.close if hasattr(b, "close") else b["close"])
            for b in ohlcv[-(bars + 1):]
        ]
        return (closes[-1] - closes[0]) / closes[0] * 100
    except Exception:
        return None


def _asset_class_for(symbol: str) -> AssetClass:
    """Best-effort asset class mapping."""
    s = symbol.upper()
    if any(x in s for x in ("BTC", "ETH", "SOL", "BNB")):
        return AssetClass.CRYPTO
    if s in ("USOIL", "UKOIL", "NATGAS"):
        return AssetClass.COMMODITY
    if s in ("XAUUSD", "XAGUSD", "XPTUSD"):
        return AssetClass.METAL
    if s in ("SP500", "NAS100", "UK100", "GER40"):
        return AssetClass.STOCK
    return AssetClass.FOREX


# ─────────────────────────────────────────────────────────────────────────────
#  1. CORRELATION CONFIRMATION SCORER
# ─────────────────────────────────────────────────────────────────────────────

async def correlation_confirmation(
    signal: TradingSignal,
    state: BotState,
) -> ConfirmationResult:
    """
    For each correlated asset defined in STATIC_CORRELATIONS:
      - Positive-correlated asset moves SAME direction  → +0.5
      - Negative-correlated asset moves OPPOSITE        → +0.5
      - Contradiction                                   → -0.7
    Final boost clamped to [-2.0, +2.0].
    """
    corr = STATIC_CORRELATIONS.get(signal.symbol.upper())
    if not corr:
        return ConfirmationResult(boost=0.0, confirmations=0, contradictions=0, detail=[])

    confirmations = 0
    contradictions = 0
    detail: list = []

    # ── Positive correlations ─────────────────────────────────────────────
    for asset in corr.get("positive", []):
        if asset not in state.ohlcv_cache and asset not in state.quotes:
            continue
        asset_dir = _get_momentum_direction(asset, state)
        if asset_dir is None:
            detail.append(f"  {asset:10s} → inconclusive (no data)")
            continue
        sig_dir = signal.direction.value if hasattr(signal.direction, "value") else signal.direction
        if asset_dir == sig_dir:
            confirmations += 1
            detail.append(f"  OK {asset:10s} → {asset_dir} (correlated, CONFIRMS)")
        else:
            contradictions += 1
            detail.append(f"  XX {asset:10s} → {asset_dir} (correlated, CONTRADICTS)")

    # ── Negative correlations ─────────────────────────────────────────────
    sig_dir = signal.direction.value if hasattr(signal.direction, "value") else signal.direction
    opposite = "SELL" if sig_dir == "BUY" else "BUY"
    for asset in corr.get("negative", []):
        if asset not in state.ohlcv_cache and asset not in state.quotes:
            continue
        asset_dir = _get_momentum_direction(asset, state)
        if asset_dir is None:
            detail.append(f"  {asset:10s} → inconclusive (no data)")
            continue
        if asset_dir == opposite:
            confirmations += 1
            detail.append(f"  OK {asset:10s} → {asset_dir} (inverse-correlated, CONFIRMS)")
        else:
            contradictions += 1
            detail.append(f"  XX {asset:10s} → {asset_dir} (inverse-correlated, CONTRADICTS)")

    # ── Dynamic Pearson enrichment (opportunistic) ────────────────────────
    dyn_adjustment = 0.0
    known_assets = list(state.ohlcv_cache.keys())
    if known_assets:
        dyn_results = _dyn_engine.get_all_correlations(
            signal.symbol, known_assets[:8], timeframe="H1"
        )
        for dyn in dyn_results:
            if not dyn.is_reliable:
                continue
            partner_dir = _get_momentum_direction(dyn.symbol_b, state)
            if partner_dir is None:
                continue
            sig_dir = signal.direction.value if hasattr(signal.direction, "value") else signal.direction
            if dyn.coefficient >= 0.70 and partner_dir == sig_dir:
                dyn_adjustment += 0.2
                detail.append(f"  {dyn.symbol_b:10s} Pearson={dyn.coefficient:+.2f} CONFIRMS (dynamic)")
            elif dyn.coefficient <= -0.70 and partner_dir == opposite:
                dyn_adjustment += 0.2
                detail.append(f"  {dyn.symbol_b:10s} Pearson={dyn.coefficient:+.2f} CONFIRMS inverse (dynamic)")

    raw_boost = (confirmations * 0.5) - (contradictions * 0.7) + dyn_adjustment
    boost = max(-2.0, min(2.0, raw_boost))

    return ConfirmationResult(
        boost=round(boost, 2),
        confirmations=confirmations,
        contradictions=contradictions,
        detail=detail,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  2. LEADING INDICATOR PRE-FILTER
# ─────────────────────────────────────────────────────────────────────────────

async def leading_indicator_check(
    signal: TradingSignal,
    state: BotState,
) -> LeadingResult:
    """
    Checks whether leading indicators have already moved in the required direction.
    If the leader hasn't moved yet → signal is early → reduce confidence.
    """
    corr = STATIC_CORRELATIONS.get(signal.symbol.upper())
    if not corr:
        return LeadingResult(aligned=True, warnings=[], confidence_factor=1.0)

    warnings: list = []
    penalties = 0
    leaders_checked = 0
    sig_dir = signal.direction.value if hasattr(signal.direction, "value") else signal.direction

    for leader in corr.get("leading", []):
        if leader not in state.ohlcv_cache and leader not in state.quotes:
            continue

        leaders_checked += 1
        leader_roc = _get_roc(leader, state, bars=5)
        if leader_roc is None:
            continue

        leader_corr = STATIC_CORRELATIONS.get(signal.symbol.upper(), {})
        is_positive = leader in leader_corr.get("positive", [])
        is_negative = leader in leader_corr.get("negative", [])

        if sig_dir == "BUY":
            if is_positive and leader_roc < -0.05:
                warnings.append(
                    f"Leading indicator {leader} falling ({leader_roc:+.3f}%) "
                    f"while signal is BUY — may be premature"
                )
                penalties += 1
            elif is_negative and leader_roc > 0.05:
                warnings.append(
                    f"Leading indicator {leader} rising ({leader_roc:+.3f}%) "
                    f"while signal is BUY — inverse leader not cooperating"
                )
                penalties += 1
        else:  # SELL
            if is_positive and leader_roc > 0.05:
                warnings.append(
                    f"Leading indicator {leader} rising ({leader_roc:+.3f}%) "
                    f"while signal is SELL — may be premature"
                )
                penalties += 1
            elif is_negative and leader_roc < -0.05:
                warnings.append(
                    f"Leading indicator {leader} falling ({leader_roc:+.3f}%) "
                    f"while signal is SELL — inverse leader not cooperating"
                )
                penalties += 1

    if leaders_checked == 0:
        return LeadingResult(aligned=True, warnings=[], confidence_factor=1.0)

    confidence_factor = max(0.70, 1.0 - (penalties * 0.10))
    aligned = penalties == 0

    return LeadingResult(
        aligned=aligned,
        warnings=warnings,
        confidence_factor=round(confidence_factor, 2),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  3. DIVERGENCE SIGNAL DETECTOR
# ─────────────────────────────────────────────────────────────────────────────

async def detect_divergence_signals(state: BotState) -> list:
    """
    Scans DIVERGENCE_PAIRS for catch-up opportunities.

    A divergence signal fires when:
      - The leader has moved significantly (>= threshold)
      - The lagger has barely moved (<= 30% of threshold)
      - The expected directional relationship holds
    """
    candidates: list = []

    for leader, lagger, same_direction, threshold, sig_symbol, sig_dir in DIVERGENCE_PAIRS:
        leader_chg = _get_session_change_pct(leader, state)
        lagger_chg = _get_session_change_pct(lagger, state)

        if leader_chg is None or lagger_chg is None:
            continue

        if abs(leader_chg) < abs(threshold):
            continue

        correct_direction = (leader_chg > 0) == (threshold > 0)
        if not correct_direction:
            continue

        lagger_lagging = abs(lagger_chg) < abs(threshold) * 0.30
        if not lagger_lagging:
            continue

        # Don't generate a divergence signal if it contradicts an existing open position
        existing = next(
            (t for t in state.open_trades if t.symbol == sig_symbol), None
        )
        if existing:
            existing_dir = existing.direction.value if hasattr(existing.direction, "value") else existing.direction
            if existing_dir != sig_dir:
                continue

        reasoning = (
            f"DIVERGENCE: {leader} moved {leader_chg:+.3f}% "
            f"but {lagger} only moved {lagger_chg:+.3f}% — "
            f"catch-up expected on {sig_symbol} {sig_dir}"
        )

        strength_ratio = min(2.0, abs(leader_chg) / abs(threshold))
        confidence = round(min(0.80, 0.60 + strength_ratio * 0.10), 2)

        candidates.append(DivergenceSignal(
            symbol=sig_symbol,
            direction=sig_dir,
            score=7.0,
            confidence=confidence,
            leader=leader,
            leader_change=round(leader_chg, 4),
            lagger_change=round(lagger_chg, 4),
            reasoning=reasoning,
        ))
        log.info(
            "[CORR] DIVERGENCE: {} moved {:.3f}% — {} {} expected (conf {:.0%})",
            leader, leader_chg, sig_symbol, sig_dir, confidence,
        )

    return candidates


def _divergence_to_signal(div: DivergenceSignal, state: BotState) -> Optional[TradingSignal]:
    """Convert a DivergenceSignal to a TradingSignal using live quote data."""
    quote = state.quotes.get(div.symbol)
    if not quote:
        return None

    mid = (quote.bid + quote.ask) / 2
    atr_proxy = quote.spread * 50

    bars = state.ohlcv_cache.get(div.symbol)
    if bars and len(bars) >= 15:
        try:
            highs  = [float(b.high  if hasattr(b,"high")  else b["high"])  for b in bars[-15:]]
            lows   = [float(b.low   if hasattr(b,"low")   else b["low"])   for b in bars[-15:]]
            closes = [float(b.close if hasattr(b,"close") else b["close"]) for b in bars[-15:]]
            trs = [
                max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
                for i in range(1, len(highs))
            ]
            atr_proxy = float(np.mean(trs))
        except Exception:
            pass

    is_buy = div.direction == "BUY"
    sl     = round(mid - atr_proxy * 1.5, 5) if is_buy else round(mid + atr_proxy * 1.5, 5)
    tp     = round(mid + atr_proxy * 2.5, 5) if is_buy else round(mid - atr_proxy * 2.5, 5)
    sl_dist = abs(mid - sl)
    tp_dist = abs(mid - tp)
    rr = round(tp_dist / sl_dist, 2) if sl_dist > 0 else 0.0

    return TradingSignal(
        id=str(uuid.uuid4()),
        symbol=div.symbol,
        asset_class=_asset_class_for(div.symbol),
        direction=Direction(div.direction),
        score=div.score,
        confidence=div.confidence,
        strength=SignalStrength.MEDIUM,
        strategy="correlation_divergence",
        timeframe="H1",
        entry_price=round(mid, 5),
        stop_loss=sl,
        take_profit=tp,
        risk_reward=rr,
        reasoning=div.reasoning,
        metadata={
            "leader":        div.leader,
            "leader_change": div.leader_change,
            "lagger_change": div.lagger_change,
            "source":        "divergence_detector",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
#  4. CORRELATION-ADJUSTED LOT SIZE
# ─────────────────────────────────────────────────────────────────────────────

def correlation_adjusted_lot_size(
    signal: TradingSignal,
    open_trades: list,
    base_lot_size: float,
) -> tuple:
    """
    Scale down lot size when correlated positions are already open.

      0 existing same-direction positions in group → 100% size
      1 existing                                   →  70% size
      2 existing                                   →  50% size
      3 or more                                    →  35% size
    """
    group = _get_group(signal.symbol)
    if group is None:
        return base_lot_size, "no correlation group — full size"

    group_members = CORR_GROUP_MEMBERS.get(group, [])
    sig_dir = signal.direction.value if hasattr(signal.direction, "value") else signal.direction
    same_dir_count = sum(
        1 for t in open_trades
        if t.symbol in group_members
        and t.symbol != signal.symbol
        and (t.direction.value if hasattr(t.direction, "value") else t.direction) == sig_dir
    )

    scale_factors = {0: 1.00, 1: 0.70, 2: 0.50, 3: 0.35}
    scale = scale_factors.get(min(same_dir_count, 3), 0.35)
    adjusted = round(base_lot_size * scale, 2)
    adjusted = max(adjusted, 0.01)

    reason = (
        f"group={group}, existing_same_dir={same_dir_count}, "
        f"scale={scale:.0%}, lot={base_lot_size}→{adjusted}"
    )
    return adjusted, reason


# ─────────────────────────────────────────────────────────────────────────────
#  5. GROUP CONCENTRATION VETO
# ─────────────────────────────────────────────────────────────────────────────

def check_group_concentration(
    signal: TradingSignal,
    open_trades: list,
) -> tuple:
    """
    Returns (allowed, reason).
    allowed=False means the signal must be rejected due to group concentration.
    """
    group = _get_group(signal.symbol)
    if group is None:
        return True, "no group"

    max_allowed = GROUP_MAX_SAME_DIRECTION.get(group, 2)
    if max_allowed == 0:
        return False, f"symbol in reference-only group '{group}' — not traded directly"

    group_members = CORR_GROUP_MEMBERS.get(group, [])
    sig_dir = signal.direction.value if hasattr(signal.direction, "value") else signal.direction
    existing_same_dir = [
        t for t in open_trades
        if t.symbol in group_members
        and (t.direction.value if hasattr(t.direction, "value") else t.direction) == sig_dir
    ]

    if len(existing_same_dir) >= max_allowed:
        return False, (
            f"group '{group}' already has {len(existing_same_dir)} "
            f"{sig_dir} positions (max {max_allowed})"
        )

    return True, f"group '{group}' has {len(existing_same_dir)}/{max_allowed} positions — OK"


# ─────────────────────────────────────────────────────────────────────────────
#  SINGLE SIGNAL EVALUATOR
# ─────────────────────────────────────────────────────────────────────────────

async def _evaluate_signal(
    signal: TradingSignal,
    state: BotState,
) -> tuple:
    """Evaluate a single signal through the correlation pipeline. Returns (accepted, signal)."""

    # Step 1: Group concentration veto
    allowed, conc_reason = check_group_concentration(signal, state.open_trades)
    if not allowed:
        log.info("[CORR] REJECTED {} {} — group veto: {}",
                 signal.direction, signal.symbol, conc_reason)
        return False, signal

    # Step 2: Correlation confirmation score
    conf_result = await correlation_confirmation(signal, state)
    original_score = signal.score
    signal.score = round(min(10.0, max(0.0, signal.score + conf_result.boost)), 2)
    signal.metadata["correlation_boost"]   = conf_result.boost
    signal.metadata["corr_confirmations"]  = conf_result.confirmations
    signal.metadata["corr_contradictions"] = conf_result.contradictions

    log.info(
        "[CORR] {} {} | score {:.1f}→{:.1f} | confirms={} contradicts={} | boost={:+.2f}",
        signal.direction, signal.symbol,
        original_score, signal.score,
        conf_result.confirmations, conf_result.contradictions,
        conf_result.boost,
    )
    for line in conf_result.detail:
        log.debug("   {}", line)

    # Step 3: Reject if too many contradictions
    REJECTION_BOOST_THRESHOLD = -1.0
    if conf_result.boost < REJECTION_BOOST_THRESHOLD:
        log.info(
            "[CORR] REJECTED {} {} — correlation boost {:.2f} < {:.2f}",
            signal.direction, signal.symbol,
            conf_result.boost, REJECTION_BOOST_THRESHOLD,
        )
        return False, signal

    # Step 4: Leading indicator check
    leading = await leading_indicator_check(signal, state)
    if not leading.aligned:
        original_conf = signal.confidence
        signal.confidence = round(signal.confidence * leading.confidence_factor, 3)
        signal.metadata["leading_factor"]   = leading.confidence_factor
        signal.metadata["leading_warnings"] = leading.warnings
        for w in leading.warnings:
            log.warning("[CORR] Leading indicator: {} {} — {}", signal.symbol, signal.direction, w)
        log.info(
            "[CORR] {} {} confidence adjusted {:.0%}→{:.0%} (leading factor {:.0%})",
            signal.direction, signal.symbol,
            original_conf, signal.confidence, leading.confidence_factor,
        )

    # Step 5: Correlation-adjusted lot size
    base_lot = signal.metadata.get("lot_size", 0.01)
    adj_lot, size_reason = correlation_adjusted_lot_size(
        signal, state.open_trades, base_lot
    )
    if adj_lot != base_lot:
        signal.metadata["lot_size"]        = adj_lot
        signal.metadata["lot_size_base"]   = base_lot
        signal.metadata["lot_size_reason"] = size_reason
        log.info(
            "[CORR] {} {} lot size adjusted {:.2f}→{:.2f} ({})",
            signal.direction, signal.symbol, base_lot, adj_lot, size_reason,
        )

    return True, signal


# ─────────────────────────────────────────────────────────────────────────────
#  SUMMARY HELPER  (used by orchestrator for LLM context)
# ─────────────────────────────────────────────────────────────────────────────

def build_correlation_summary(signal: TradingSignal) -> str:
    """Build a human-readable correlation summary for LLM prompts."""
    meta = signal.metadata
    lines = [f"Correlation analysis for {signal.symbol} {signal.direction}:"]

    boost = meta.get("correlation_boost")
    if boost is not None:
        lines.append(
            f"  Score adjustment: {boost:+.2f} "
            f"({meta.get('corr_confirmations',0)} confirms, "
            f"{meta.get('corr_contradictions',0)} contradicts)"
        )

    warnings = meta.get("leading_warnings", [])
    if warnings:
        lines.append("  Leading indicator warnings:")
        for w in warnings:
            lines.append(f"    - {w}")

    if meta.get("source") == "divergence_detector":
        lines.append(
            f"  SOURCE: Divergence signal — "
            f"{meta.get('leader')} moved {meta.get('leader_change',0):+.3f}% "
            f"but {signal.symbol} only moved {meta.get('lagger_change',0):+.3f}%"
        )

    lot_reason = meta.get("lot_size_reason")
    if lot_reason and meta.get("lot_size_base") != meta.get("lot_size"):
        lines.append(f"  Lot size: {lot_reason}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN AGENT NODE
# ─────────────────────────────────────────────────────────────────────────────

async def correlation_manager_node(state: BotState) -> BotState:
    """
    LangGraph node — runs after market_analyst, before sentiment_agent.

    Steps per signal:
      1. Group concentration veto        (hard reject if group is full)
      2. Correlation confirmation score  (boost / reduce signal score)
      3. Leading indicator check         (reduce confidence if leaders not aligned)
      4. Reject if net boost < -1.0      (majority of related assets contradict)
      5. Adjust lot size for correlation (scale down if correlated positions open)

    Additional:
      6. Detect divergence signals and inject into pending_signals
    """
    log.info(
        "[CORR] CorrelationManager: Evaluating {} signals | {} open trades",
        len(state.pending_signals), len(state.open_trades),
    )

    if not state.pending_signals:
        # Still run divergence detection even with no pending signals
        divs = await detect_divergence_signals(state)
        for div in divs:
            sig = _divergence_to_signal(div, state)
            if sig and sig.risk_reward >= 1.5:
                state.pending_signals.append(sig)
                log.info("[CORR] Injected divergence signal: {} {} score={:.1f}",
                         sig.symbol, sig.direction, sig.score)
        return state

    enhanced: list = []

    # Process all signals concurrently
    tasks = [_evaluate_signal(signal, state) for signal in state.pending_signals]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for signal, result in zip(state.pending_signals, results):
        if isinstance(result, Exception):
            log.error("[CORR] Error evaluating {}: {}", signal.symbol, result)
            enhanced.append(signal)   # pass through unchanged on error
            continue
        accepted, final_signal = result
        if accepted:
            enhanced.append(final_signal)

    # ── Divergence detection ──────────────────────────────────────────────
    divs = await detect_divergence_signals(state)
    for div in divs:
        already = any(
            s.symbol == div.symbol and
            (s.direction.value if hasattr(s.direction, "value") else s.direction) == div.direction
            for s in enhanced
        )
        if already:
            continue

        sig = _divergence_to_signal(div, state)
        if sig is None:
            continue

        allowed, reason = check_group_concentration(sig, state.open_trades)
        if not allowed:
            log.info("[CORR] Divergence signal {} {} rejected: {}", sig.symbol, sig.direction, reason)
            continue

        if sig.risk_reward >= 1.5:
            enhanced.append(sig)
            log.info("[CORR] Divergence signal added: {} {} score={:.1f} conf={:.0%}",
                     sig.symbol, sig.direction, sig.score, sig.confidence)

    passed_original = len([s for s in enhanced if s.strategy != "correlation_divergence"])
    divergence_added = len([s for s in enhanced if s.strategy == "correlation_divergence"])
    rejected = len(state.pending_signals) - passed_original

    log.info(
        "[CORR] {}/{} signals passed (+{} divergence) | {} rejected",
        passed_original,
        len(state.pending_signals),
        divergence_added,
        rejected,
    )

    state.pending_signals = enhanced
    return state

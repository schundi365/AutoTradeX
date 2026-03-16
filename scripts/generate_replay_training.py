"""
APEX Bot — Replay Training Data Generator

Generates realistic labelled fine-tuning examples from collected historical
OHLCV + macro CSV data — no need to wait for 200 real paper-trade decisions.

For each sampled bar the script:
  1. Computes RSI / ADX / ATR / EMA indicators on XAUUSD (or other assets)
  2. Joins DXY + US10Y intraday change + FRED macro regime
  3. Applies APEX trading rules to decide APPROVE / REJECT + reasoning
  4. Simulates the trade outcome (WIN / LOSS) using forward price data
  5. Writes an Alpaca-format training example identical to prepare_training_data.py

Output: training_data/apex_training_replay_YYYY-MM-DD.jsonl
        training_data/apex_training_latest.jsonl  (appended / replaced)

Usage:
    python scripts/generate_replay_training.py
    python scripts/generate_replay_training.py --assets XAUUSD EURUSD BTC
    python scripts/generate_replay_training.py --samples 400 --step 6
    python scripts/generate_replay_training.py --append   # merge with existing latest
"""
from __future__ import annotations
import argparse
import json
import random
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import settings as _settings

# ─────────────────────────────────────────────────────────────────────────────
# Indicator helpers (no extra deps — pure pandas/numpy)
# ─────────────────────────────────────────────────────────────────────────────

def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0.0)
    loss  = (-delta).clip(lower=0.0)
    avg_g = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_l = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs    = avg_g / avg_l.replace(0, 1e-10)
    return 100.0 - 100.0 / (1.0 + rs)


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder-smoothed ADX."""
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)

    up_move   = high - high.shift()
    down_move = low.shift() - low

    dm_plus  = np.where((up_move > down_move) & (up_move > 0), up_move,  0.0)
    dm_minus = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    dm_plus  = pd.Series(dm_plus,  index=close.index)
    dm_minus = pd.Series(dm_minus, index=close.index)

    atr14    = tr.ewm(alpha=1/period, adjust=False).mean()
    di_plus  = 100 * dm_plus.ewm( alpha=1/period, adjust=False).mean() / atr14
    di_minus = 100 * dm_minus.ewm(alpha=1/period, adjust=False).mean() / atr14

    denom = (di_plus + di_minus).replace(0, 1e-10)
    dx    = 100 * (di_plus - di_minus).abs() / denom
    return dx.ewm(alpha=1/period, adjust=False).mean()


# ─────────────────────────────────────────────────────────────────────────────
# Regime + scoring helpers
# ─────────────────────────────────────────────────────────────────────────────

def _regime(adx_val: float) -> str:
    if adx_val >= 35:
        return "BREAKOUT"
    if adx_val >= 25:
        return "STRONG_TREND"
    if adx_val >= 15:
        return "WEAK_TREND"
    return "RANGING"


def _min_score(regime: str) -> float:
    return {"BREAKOUT": 8.0, "STRONG_TREND": 7.5, "WEAK_TREND": 7.0, "RANGING": 7.5}[regime]


def _compute_score(
    direction: str,
    rsi_val: float,
    adx_val: float,
    regime: str,
    dxy_change: float,
    us10y_change_bps: float,
    macro_regime: str,
) -> float:
    """Simplified but realistic signal score (0-10)."""
    score = 5.0

    # RSI alignment (BUY: 45-65 ideal, SELL: 35-55 ideal)
    if direction == "BUY":
        if 45 <= rsi_val <= 65:
            score += 2.0
        elif rsi_val < 35:
            score += 0.5   # oversold rebound potential
        elif rsi_val > 75:
            score -= 1.5   # overbought
    else:  # SELL
        if 35 <= rsi_val <= 55:
            score += 2.0
        elif rsi_val > 65:
            score += 0.5
        elif rsi_val < 25:
            score -= 1.5

    # ADX
    if adx_val >= 30:
        score += 2.0
    elif adx_val >= 20:
        score += 1.0
    elif adx_val < 15:
        score -= 1.0

    # Macro (gold/BUY friendly = weak DXY + risk-on)
    if direction == "BUY":
        if dxy_change < -0.3:
            score += 1.0
        elif dxy_change > 0.5:
            score -= 1.0
        if us10y_change_bps < -3:
            score += 0.5
        if macro_regime == "RISK_ON":
            score += 0.5
        elif macro_regime in ("RISK_OFF", "SEVERE_RISK_OFF"):
            score -= 0.5
    else:
        if dxy_change > 0.3:
            score += 1.0
        elif dxy_change < -0.5:
            score -= 1.0

    return round(min(max(score, 0.0), 10.0), 1)


def _confidence(score: float, adx_val: float, macro_regime: str) -> float:
    base = (score / 10.0) * 0.7 + (min(adx_val, 40) / 40.0) * 0.3
    if macro_regime in ("RISK_ON", "RISK_OFF"):
        base = min(base + 0.05, 1.0)
    return round(base, 2)


# ─────────────────────────────────────────────────────────────────────────────
# Decision + reasoning
# ─────────────────────────────────────────────────────────────────────────────

def _make_decision(
    direction: str,
    score: float,
    regime: str,
    dxy_change: float,
    macro_regime: str,
) -> tuple[str, list[str], str | None]:
    """Returns (decision, reasoning_lines, reject_reason)."""

    # Hard vetoes
    if macro_regime == "SEVERE_RISK_OFF" and direction == "BUY":
        return "REJECT", [
            f"MACRO VETO: DXY {dxy_change:+.2f}% triggers SEVERE RISK_OFF — no BUY trades",
            "YIELD VETO: Rising yields are a headwind for Gold",
        ], "SEVERE_RISK_OFF"

    if score < _min_score(regime):
        return "REJECT", [
            f"SCORE LOW: {score:.1f} below {_min_score(regime):.1f} threshold for {regime} regime",
            f"TREND: ADX insufficient for conviction trade in current regime",
        ], "LOW_SCORE"

    return "APPROVE", [], None


def _build_reasoning(
    direction: str,
    rsi_val: float,
    adx_val: float,
    atr_pct: float,
    regime: str,
    dxy_change: float,
    us10y_change_bps: float,
    macro_regime: str,
    sentiment: float,
    decision: str,
    reject_reason: str | None,
) -> list[str]:
    lines = []
    i = 1

    if decision == "APPROVE":
        # Trend
        trend_word = "bullish" if direction == "BUY" else "bearish"
        lines.append(f"{i}. TREND: EMA structure confirms {trend_word} bias")
        i += 1
        # Momentum
        lines.append(f"{i}. MOMENTUM: RSI {rsi_val:.1f} {'in bullish zone' if direction=='BUY' else 'in bearish zone'} with room to run")
        i += 1
        # Trend strength
        if adx_val >= 25:
            lines.append(f"{i}. TREND STRENGTH: ADX {adx_val:.1f} confirms genuine trend, not noise")
        else:
            lines.append(f"{i}. TREND STRENGTH: ADX {adx_val:.1f} — moderate, use reduced lot size")
        i += 1
        # Macro
        if abs(dxy_change) > 0.1 or abs(us10y_change_bps) > 2:
            dxy_dir = "Falling" if dxy_change < 0 else "Rising"
            yield_dir = "falling" if us10y_change_bps < 0 else "rising"
            lines.append(
                f"{i}. MACRO: {dxy_dir} DXY ({dxy_change:+.2f}%) and {yield_dir} yields "
                f"({us10y_change_bps:+.0f}bps) — {'Gold tailwinds' if direction=='BUY' and dxy_change<0 else 'aligned'}"
            )
            i += 1
        # Sentiment
        if abs(sentiment) > 0.1:
            lines.append(f"{i}. SENTIMENT: Avg sentiment {sentiment:+.2f} — {'supports' if sentiment > 0 else 'caution'} {direction} direction")
            i += 1
        # Calendar placeholder
        lines.append(f"{i}. CALENDAR: No high-impact events within execution window")
        # Entry details
        lines.append(f"\nENTRY: Market | STOP: -1.5×ATR | TARGET: +2.5×ATR | ATR%: {atr_pct:.2f}%")
        lines.append("RISK_REWARD: 2.5:1" + (" | Lot: 80% (weak trend)" if adx_val < 20 else ""))

    else:  # REJECT
        for r in [
            (reject_reason == "SEVERE_RISK_OFF",
             f"MACRO VETO: DXY {dxy_change:+.2f}% triggers SEVERE RISK_OFF — no BUY trades allowed"),
            (reject_reason == "LOW_SCORE",
             f"SCORE LOW: {adx_val:.1f} ADX / RSI {rsi_val:.1f} insufficient for {regime} regime"),
            (macro_regime in ("RISK_OFF", "SEVERE_RISK_OFF") and direction == "BUY",
             "MACRO: Risk-off environment unfavourable for Gold BUY"),
            (adx_val < 15,
             f"WEAK TREND: ADX {adx_val:.1f} below 15 — no meaningful directional move"),
            (True,
             f"WAIT FOR: Stronger setup. Re-check when ADX > 20 and score > {_min_score(regime):.0f}"),
        ]:
            if r[0]:
                lines.append(f"{len(lines)+1}. {r[1]}")
                if len(lines) >= 3:
                    break

    return lines


def _build_reasoning_lines(
    direction, rsi_val, adx_val, atr_pct, regime,
    dxy_change, us10y_change_bps, macro_regime, sentiment,
    decision, reject_reason,
):
    """Non-generator wrapper for _build_reasoning."""
    result = []
    i = 1

    if decision == "APPROVE":
        trend_word = "bullish" if direction == "BUY" else "bearish"
        result.append(f"{i}. TREND: EMA structure confirms {trend_word} bias"); i += 1
        result.append(f"{i}. MOMENTUM: RSI {rsi_val:.1f} {'in bullish zone' if direction=='BUY' else 'in bearish zone'} with room to run"); i += 1
        if adx_val >= 25:
            result.append(f"{i}. TREND STRENGTH: ADX {adx_val:.1f} confirms genuine trend, not noise")
        else:
            result.append(f"{i}. TREND STRENGTH: ADX {adx_val:.1f} — moderate, use reduced lot size")
        i += 1
        if abs(dxy_change) > 0.1 or abs(us10y_change_bps) > 2:
            dxy_dir  = "Falling" if dxy_change < 0 else "Rising"
            yld_dir  = "falling" if us10y_change_bps < 0 else "rising"
            tail_str = "Gold tailwinds" if direction == "BUY" and dxy_change < 0 else "aligned with direction"
            result.append(f"{i}. MACRO: {dxy_dir} DXY ({dxy_change:+.2f}%) and {yld_dir} yields ({us10y_change_bps:+.0f}bps) — {tail_str}"); i += 1
        if abs(sentiment) > 0.1:
            tone = "supports" if sentiment > 0 else "caution —"
            result.append(f"{i}. SENTIMENT: Avg sentiment {sentiment:+.2f} — {tone} {direction} direction"); i += 1
        result.append(f"{i}. CALENDAR: No high-impact events within execution window")
        result.append(f"\nENTRY: Market | STOP: -1.5×ATR | TARGET: +2.5×ATR | ATR%: {atr_pct:.2f}%")
        lot_note = " | Lot: 80% (weak trend)" if adx_val < 20 else ""
        result.append(f"RISK_REWARD: 2.5:1{lot_note}")
    else:
        pairs = [
            (reject_reason == "SEVERE_RISK_OFF",
             f"MACRO VETO: DXY {dxy_change:+.2f}% triggers SEVERE RISK_OFF — no BUY trades allowed"),
            (reject_reason == "LOW_SCORE",
             f"SIGNAL WEAK: ADX {adx_val:.1f} and score insufficient for {regime} regime threshold"),
            (macro_regime in ("RISK_OFF", "SEVERE_RISK_OFF") and direction == "BUY",
             "MACRO: Risk-off environment unfavourable for Gold BUY"),
            (adx_val < 15,
             f"WEAK TREND: ADX {adx_val:.1f} below 15 — no directional conviction"),
            (True,
             f"WAIT FOR: Setup improvement — ADX > 20, score > {_min_score(regime):.0f}"),
        ]
        idx = 1
        for cond, text in pairs:
            if cond:
                result.append(f"{idx}. {text}"); idx += 1
            if idx > 4:
                break

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Forward outcome simulation
# ─────────────────────────────────────────────────────────────────────────────

def _simulate_outcome(
    df: pd.DataFrame,
    entry_idx: int,
    direction: str,
    atr_val: float,
    lookahead: int = 20,
    lot_size: float = 0.1,
) -> tuple[str, float]:
    """Look forward `lookahead` bars; simulate TP/SL hit.

    Returns (outcome, pnl_usd) where outcome is 'WIN' | 'LOSS' | 'FLAT'.
    XAUUSD: 1 point = $1 per 1-lot → pnl = Δprice × lot_size × 100
    """
    entry_price = df["close"].iloc[entry_idx]
    sl = 1.5 * atr_val
    tp = 2.5 * atr_val

    futures = df["close"].iloc[entry_idx + 1: entry_idx + 1 + lookahead]
    if futures.empty:
        return "FLAT", 0.0

    for price in futures:
        if direction == "BUY":
            if price >= entry_price + tp:
                return "WIN",  round(tp  * lot_size * 100, 2)
            if price <= entry_price - sl:
                return "LOSS", round(-sl * lot_size * 100, 2)
        else:
            if price <= entry_price - tp:
                return "WIN",  round(tp  * lot_size * 100, 2)
            if price >= entry_price + sl:
                return "LOSS", round(-sl * lot_size * 100, 2)

    # Neither hit — close at last future bar
    last = futures.iloc[-1]
    pnl_pts = (last - entry_price) * (1 if direction == "BUY" else -1)
    return "FLAT", round(pnl_pts * lot_size * 100, 2)


# ─────────────────────────────────────────────────────────────────────────────
# Main generation function
# ─────────────────────────────────────────────────────────────────────────────

SYMBOL_FILE_MAP = {
    "XAUUSD": "XAUUSD_1h.csv",
    "EURUSD": "EURUSD_1h.csv",
    "GBPUSD": "GBPUSD_1h.csv",
    "USDJPY": "USDJPY_1h.csv",
    "AUDUSD": "AUDUSD_1h.csv",
    "BTC":    "BTC_1h.csv",
    "ETH":    "ETH_1h.csv",
}

# Symbol → DuckDB timeframe name (fallback when CSV has too few rows)
SYMBOL_DB_TIMEFRAME = {
    "XAUUSD": "H1",
    "EURUSD": "H1",
    "GBPUSD": "H1",
    "USDJPY": "H1",
    "AUDUSD": "H1",
}

_MIN_CSV_BARS = 200  # fewer than this → try DuckDB fallback

INSTRUCTION = "You are a trading decision engine. Reply with GO or NOGO only — one word, nothing else."


def _load_from_duckdb(symbol: str, timeframe: str = "H1") -> pd.DataFrame | None:
    """Fall back to market_data.duckdb when the raw CSV is missing or too small."""
    db_path = Path("data/market_data.duckdb")
    if not db_path.exists():
        return None
    try:
        import duckdb
        con = duckdb.connect(str(db_path), read_only=True)
        df = con.execute(
            "SELECT timestamp, open, high, low, close, 0.0 AS volume "
            "FROM ohlcv WHERE symbol=? AND timeframe=? ORDER BY timestamp",
            [symbol, timeframe],
        ).df()
        con.close()
        if df.empty:
            return None
        # Normalise timestamps to UTC-aware
        df["ts"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.drop(columns=["timestamp"])
        df = df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
        return df
    except Exception as e:
        print(f"  DuckDB fallback error: {e}")
        return None


def generate_for_symbol(
    symbol: str,
    raw_dir: Path,
    dxy_df: pd.DataFrame,
    us10y_df: pd.DataFrame,
    fred_df: pd.DataFrame,
    step: int = 4,
    max_samples: int = 200,
    seed: int = 42,
) -> list[dict]:
    """Generate training examples for one symbol. Returns list of dicts."""
    rng = random.Random(seed)

    csv_name = SYMBOL_FILE_MAP.get(symbol)
    if not csv_name:
        print(f"  WARNING: No CSV mapping for {symbol} — skipping")
        return []

    csv_path = raw_dir / csv_name
    df = None

    if csv_path.exists():
        _raw = pd.read_csv(csv_path)
        if len(_raw) >= _MIN_CSV_BARS:
            df = _raw
            df["ts"] = pd.to_datetime(df["timestamp"], utc=True)
            df = df.sort_values("ts").reset_index(drop=True)
        else:
            print(f"  {symbol}: CSV has only {len(_raw)} bars — trying DuckDB fallback...")
    else:
        print(f"  WARNING: {csv_path} not found — trying DuckDB fallback...")

    if df is None:
        tf = SYMBOL_DB_TIMEFRAME.get(symbol)
        if tf:
            df = _load_from_duckdb(symbol, tf)
        if df is None or len(df) < _MIN_CSV_BARS:
            print(f"  WARNING: {symbol} has insufficient data (need {_MIN_CSV_BARS}+ bars) — skipping")
            return []
        print(f"  {symbol}: Loaded {len(df)} bars from DuckDB ({tf})")

    # ── Indicators ────────────────────────────────────────────────────────────
    df["rsi"]   = _rsi(df["close"])
    df["adx"]   = _adx(df["high"], df["low"], df["close"])
    df["atr"]   = _atr(df["high"], df["low"], df["close"])
    df["ema20"] = _ema(df["close"], 20)
    df["ema50"] = _ema(df["close"], 50)
    df = df.dropna().reset_index(drop=True)

    # ── Merge DXY intraday change ─────────────────────────────────────────────
    dxy_sub = dxy_df[["ts", "close"]].copy()
    dxy_sub["dxy_change_pct"] = dxy_sub["close"].pct_change() * 100
    dxy_sub = dxy_sub.rename(columns={"close": "dxy_close"})

    us10y_sub = us10y_df[["ts", "close"]].copy()
    us10y_sub["us10y_change_bps"] = us10y_sub["close"].diff() * 100   # yield in %, × 100 = bps
    us10y_sub = us10y_sub.rename(columns={"close": "us10y_close"})

    df = pd.merge_asof(df.sort_values("ts"), dxy_sub.sort_values("ts"),
                       on="ts", direction="backward", tolerance=pd.Timedelta("2h"))
    df = pd.merge_asof(df.sort_values("ts"), us10y_sub.sort_values("ts"),
                       on="ts", direction="backward", tolerance=pd.Timedelta("2h"))
    df = df.dropna(subset=["dxy_change_pct"]).reset_index(drop=True)

    # ── Merge FRED daily macro regime ─────────────────────────────────────────
    fred_sub = fred_df[["date", "macro_regime", "DXY_change_pct", "US10Y_change_bps"]].copy()
    fred_sub["ts"] = pd.to_datetime(fred_sub["date"], utc=True)
    df["date_only"] = df["ts"].dt.date.astype(str)
    fred_sub["date_only"] = fred_sub["date"]
    df = df.merge(fred_sub[["date_only", "macro_regime"]].rename(
        columns={"macro_regime": "macro_regime_daily"}), on="date_only", how="left")
    df["macro_regime_daily"] = df["macro_regime_daily"].fillna("NEUTRAL")

    print(f"  {symbol}: {len(df)} bars after indicator + macro join")

    # ── Candidate bars (skip first 60 for warmup) ────────────────────────────
    warmup = 60
    lookahead = 20
    indices = list(range(warmup, len(df) - lookahead, step))
    rng.shuffle(indices)

    examples = []
    approve_count = reject_count = 0
    target_approve = max_samples // 2
    target_reject  = max_samples - target_approve

    for idx in indices:
        if approve_count >= target_approve and reject_count >= target_reject:
            break

        row = df.iloc[idx]

        rsi_val  = round(float(row["rsi"]),  1)
        adx_val  = round(float(row["adx"]),  1)
        atr_val  = float(row["atr"])
        atr_pct  = round(atr_val / float(row["close"]) * 100, 2)
        ema20    = float(row["ema20"])
        ema50    = float(row["ema50"])

        dxy_change       = round(float(row.get("dxy_change_pct",   0.0)), 2)
        us10y_change_bps = round(float(row.get("us10y_change_bps", 0.0)), 1)
        macro_regime     = str(row.get("macro_regime_daily", "NEUTRAL"))

        # Direction: EMA-based with small random noise for variety
        direction = "BUY" if ema20 > ema50 else "SELL"
        # Occasionally flip direction to generate counter-trend rejections
        if rng.random() < 0.25:
            direction = "SELL" if direction == "BUY" else "BUY"

        regime = _regime(adx_val)
        score  = _compute_score(direction, rsi_val, adx_val, regime,
                                 dxy_change, us10y_change_bps, macro_regime)
        confidence = _confidence(score, adx_val, macro_regime)

        # Simplified sentiment proxy from macro signals
        sentiment = round(
            -dxy_change * 0.3  # weak USD = positive Gold sentiment
            + (rsi_val - 50) / 100 * (1 if direction == "BUY" else -1)
            + (0.1 if macro_regime == "RISK_ON" else -0.1 if macro_regime in ("RISK_OFF", "SEVERE_RISK_OFF") else 0),
            2
        )
        sentiment = max(-1.0, min(1.0, sentiment))

        decision, _, reject_reason = _make_decision(
            direction, score, regime, dxy_change, macro_regime
        )

        # Balance APPROVE / REJECT
        if decision == "APPROVE" and approve_count >= target_approve:
            continue
        if decision == "REJECT" and reject_count >= target_reject:
            continue

        # Simulate outcome for APPROVE trades; REJECT has no trade
        outcome = pnl = None
        if decision == "APPROVE":
            outcome, pnl = _simulate_outcome(df, idx, direction, atr_val)
            approve_count += 1
        else:
            reject_count += 1

        reasoning = _build_reasoning_lines(
            direction, rsi_val, adx_val, atr_pct, regime,
            dxy_change, us10y_change_bps, macro_regime, sentiment,
            decision, reject_reason,
        )

        # ── Format input ──────────────────────────────────────────────────────
        input_text = (
            f"Symbol: {symbol} | Direction: {direction} | "
            f"Score: {score:.1f} | Confidence: {confidence:.2f}\n"
            f"Indicators: RSI={rsi_val} | ADX={adx_val} | ATR%={atr_pct}\n"
            f"Regime: {regime}\n"
            f"Macro: DXY change={dxy_change:+.2f}% | US10Y change={us10y_change_bps:+.1f}bps"
            f" | Macro regime={macro_regime}\n"
            f"Avg news sentiment: {sentiment:.2f}"
        )

        # ── Format output ─────────────────────────────────────────────────────
        output_text = "GO" if decision == "APPROVE" else "NOGO"

        examples.append({
            "instruction": INSTRUCTION,
            "input":  input_text,
            "output": output_text,
        })

    print(f"  {symbol}: {len(examples)} examples "
          f"(approve={approve_count}, reject={reject_count})")
    return examples


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def generate_replay_data(
    assets: list[str] | None = None,
    samples_per_asset: int = 200,
    step: int = 4,
    append: bool = False,
    out_dir: str | None = None,
    seed: int = 42,
) -> str:
    t = _settings.training
    raw_dir  = Path("data/raw")
    fred_path = Path("data/macro/fred_macro_daily.csv")
    out_path  = Path(out_dir or t.training_data_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    assets = assets or ["XAUUSD"]

    # ── Load shared macro data ────────────────────────────────────────────────
    print("Loading DXY intraday data...")
    dxy_df = pd.read_csv(raw_dir / "DXY_1h.csv")
    dxy_df["ts"] = pd.to_datetime(dxy_df["timestamp"], utc=True)
    dxy_df = dxy_df.sort_values("ts").reset_index(drop=True)

    print("Loading US10Y intraday data...")
    if (raw_dir / "US10Y_1h.csv").exists():
        us10y_df = pd.read_csv(raw_dir / "US10Y_1h.csv")
        us10y_df["ts"] = pd.to_datetime(us10y_df["timestamp"], utc=True)
        us10y_df = us10y_df.sort_values("ts").reset_index(drop=True)
    else:
        us10y_df = dxy_df.copy()  # fallback
        us10y_df["close"] = 4.3    # neutral yield placeholder

    print("Loading FRED macro regime data...")
    fred_df = pd.read_csv(fred_path)
    fred_df["date"] = fred_df["date"].astype(str)

    # ── Generate per-asset ────────────────────────────────────────────────────
    all_examples = []
    for sym in assets:
        print(f"\nGenerating examples for {sym}...")
        examples = generate_for_symbol(
            sym, raw_dir, dxy_df, us10y_df, fred_df,
            step=step, max_samples=samples_per_asset, seed=seed,
        )
        all_examples.extend(examples)

    if not all_examples:
        print("ERROR: No examples generated. Check data files in data/raw/")
        return ""

    # Shuffle the combined set
    rng = random.Random(seed)
    rng.shuffle(all_examples)

    # ── Write output ──────────────────────────────────────────────────────────
    date_str  = datetime.now().strftime("%Y-%m-%d")
    dated_out = out_path / f"apex_training_replay_{date_str}.jsonl"
    latest    = out_path / "apex_training_latest.jsonl"

    with open(dated_out, "w", encoding="utf-8") as f:
        for ex in all_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    # Merge with existing latest (if --append) or replace it
    if append and latest.exists():
        existing = [json.loads(l) for l in latest.read_text(encoding="utf-8").splitlines() if l.strip()]
        all_examples = existing + all_examples
        print(f"\nAppended to existing latest ({len(existing)} existing + {len(all_examples)-len(existing)} new = {len(all_examples)} total)")

    with open(latest, "w", encoding="utf-8") as f:
        for ex in all_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    # Stats
    approvals = sum(1 for e in all_examples if "DECISION: APPROVE" in e["output"])
    rejections = sum(1 for e in all_examples if "DECISION: REJECT"  in e["output"])
    wins  = sum(1 for e in all_examples if "OUTCOME: WIN"  in e["output"])
    losses = sum(1 for e in all_examples if "OUTCOME: LOSS" in e["output"])

    print(f"\n{'='*60}")
    print(f"Replay Training Data Generated")
    print(f"  Total examples : {len(all_examples)}")
    print(f"  Approvals      : {approvals} | Rejections: {rejections}")
    if wins + losses > 0:
        print(f"  Win rate       : {wins}/{wins+losses} = {wins/(wins+losses)*100:.1f}%")
    print(f"  Dated file     : {dated_out}")
    print(f"  Latest file    : {latest}")
    print(f"{'='*60}")
    print("Next step: Click 'Export' then 'Kaggle GPU' to fine-tune")

    return str(dated_out)


def main():
    t = _settings.training
    parser = argparse.ArgumentParser(
        description="Generate replay training data from collected historical OHLCV + macro CSVs"
    )
    parser.add_argument("--assets",  nargs="+", default=["XAUUSD"],
                        help="Asset symbols to include (default: XAUUSD)")
    parser.add_argument("--samples", type=int, default=200,
                        help="Target examples per asset (default: 200)")
    parser.add_argument("--step",    type=int, default=4,
                        help="Bar sampling step — every N bars (default: 4 = 4h)")
    parser.add_argument("--out",     default=None,
                        help=f"Output directory (default: {t.training_data_dir})")
    parser.add_argument("--append",  action="store_true",
                        help="Append to existing apex_training_latest.jsonl")
    parser.add_argument("--seed",    type=int, default=42)
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("APEX Replay Training Data Generator")
    print(f"  Assets  : {args.assets}")
    print(f"  Samples : {args.samples}/asset | Step: every {args.step} bars")
    print(f"  Append  : {args.append}")
    print(f"{'='*60}\n")

    out = generate_replay_data(
        assets=args.assets,
        samples_per_asset=args.samples,
        step=args.step,
        append=args.append,
        out_dir=args.out,
        seed=args.seed,
    )
    if not out:
        sys.exit(1)


if __name__ == "__main__":
    main()

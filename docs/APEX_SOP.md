# APEX Trading Bot — Standard Operating Procedures

> **Version 1.0 — Bot Execution Rulebook**
> Trade Entry · Multi-Position Management · Adaptive SL/TP · Risk Controls · Exit Rules

---

> 📌 **How to Use This Document**
> Every rule in this SOP is a hard constraint for the bot — not a suggestion. Rules marked **HARD VETO** cannot be overridden by any agent, signal score, or LLM decision. Rules marked **ADAPTIVE** are calculated dynamically each cycle. Rules marked **CONDITIONAL** apply only when the specified market condition is true.

---

## Section 01 — Signal Quality Gates

*Minimum conditions a signal must pass before any position is opened.*

No trade is opened unless **ALL** of the following gates pass. Any single failure results in rejection — regardless of signal score.

| # | Gate Name | Threshold | Reject Reason if Failed |
|---|-----------|-----------|------------------------|
| G1 | Minimum Signal Score | ≥ 6.5 / 10 | Score too low — setup lacks sufficient confluence |
| G2 | Minimum Confidence | ≥ 0.60 (60%) | LLM / model confidence too low to justify risk |
| G3 | Minimum Risk:Reward | ≥ 1.8 : 1 | Reward does not justify the risk at current SL/TP |
| G4 | ADX Trend Filter | ≥ 18 for momentum strategies | Market is too choppy — momentum strategies disabled |
| G5 | ATR Volatility Filter | ATR ratio 0.5× – 2.0× | Volatility too low (false breakout risk) or spike (HIGH_VOLATILE veto) |
| G6 | Volume Confirmation | Current volume ≥ 0.8× 20-bar average | Low volume = institutional absence, higher slippage risk |
| G7 | No News Blackout | No HIGH/MEDIUM event within blackout window | Calendar blackout active — entry forbidden |
| G8 | Macro Regime Check | Not SEVERE RISK_OFF (DXY > +0.8%) | Macro veto active — all trades suspended |
| G9 | Daily Drawdown | Daily loss < MAX_DAILY_DRAWDOWN_PCT | Equity protection triggered — no new trades today |
| G10 | Open Trade Cap | Open positions < MAX_OPEN_TRADES | Maximum concurrent positions reached |

---

## Section 02 — Multi-Position Entry Structure

*Pyramid into winning trades — never average into losing ones.*

APEX uses a **3-tranche position structure**. Each tranche has its own entry condition, lot size, stop loss, and take profit. This allows the bot to lock in profit on early tranches while riding the trend with the remainder.

> ⚠️ **Core Pyramid Rule**
> NEVER open Tranche 2 or 3 unless Tranche 1 is already in profit by at least 1.0 ATR. Adding to losing positions is forbidden. Pyramid only in the direction of a confirmed trend.

### 2.1 Three-Tranche Entry Model

| Tranche | Lot Size | Entry Condition | Take Profit Target | Stop Loss | Purpose |
|---------|----------|-----------------|-------------------|-----------|---------|
| **T1 — Anchor** | 40% of total planned size | Signal passes all 10 gates. Enter immediately at market. | TP1 = Entry ± (ATR × 2.0) | Initial SL = Entry ∓ (ATR × 1.5) | Establish position. Most conservative. Closes first. |
| **T2 — Builder** | 35% of total planned size | T1 is ≥ 1.0 ATR in profit AND trend indicators still aligned (EMA, ADX). | TP2 = Entry ± (ATR × 3.5) | SL = T1 entry price (breakeven on T1 cost basis) | Builds on confirmed momentum. Medium target. |
| **T3 — Runner** | 25% of total planned size | T1 is ≥ 2.0 ATR in profit AND ADX rising AND volume > 1.3× average. | TP3 = Entry ± (ATR × 5.5) or Open (trailing only) | SL = T2 entry price (locks in T1+T2 profit) | Rides the full trend. Managed by trailing stop only. |

### 2.2 Tranche Lot Size Calculation

```python
# Step 1 — Total risk budget for this trade
risk_budget  = account_balance × (MAX_RISK_PCT / 100) × risk_multiplier

# Step 2 — SL distance drives total size
total_lots   = risk_budget / (sl_distance_T1 × point_value)

# Step 3 — Split across tranches
lots_T1      = total_lots × 0.40
lots_T2      = total_lots × 0.35
lots_T3      = total_lots × 0.25

# Step 4 — Validate combined exposure
max_exposure = account_balance × (MAX_RISK_PCT × 1.5 / 100)
assert (lots_T1 + lots_T2 + lots_T3) × sl_distance_T1 × point_value <= max_exposure
```

> ✅ **Tranche Cap** — No single tranche may exceed 3% of account balance in risk even if the Kelly formula suggests more. Hard cap applies per tranche, per trade, per symbol.

### 2.3 Tranche Opening Rules

**RULE T-01: Never open T2 or T3 without T1 already open and in profit**
T2 and T3 are continuation trades, not independent entries. They confirm the trade is already working.

**RULE T-02: Maximum 1 tranche per symbol per cycle**
The bot runs on a cycle (every 5 minutes). Only one tranche may open per symbol per cycle to prevent runaway pyramiding.

**RULE T-03: T3 requires ADX confirmation**
ADX must be ≥ 25 and trending upward (current ADX > previous ADX) before T3 is opened. T3 requires a strong, accelerating trend.

**RULE T-04: All tranches share the same directional bias**
If T1 is BUY, T2 and T3 must also be BUY. Mixed-direction tranches on the same symbol are forbidden.

---

## Section 03 — Adaptive Stop Loss Management

*SL tightens as the trade develops — it never widens.*

The Stop Loss is a living parameter. It starts at an ATR-based safe distance and tightens as market conditions change. The SL can **only move in the profitable direction** — it is never moved further away from the entry price.

### 3.1 Initial SL Calculation (Adaptive by Regime)

```python
REGIME_SL_MULTIPLIERS = {
    'STRONG_TREND':  1.2,   # Tighter — clear direction, less noise
    'WEAK_TREND':    1.5,   # Standard
    'RANGING':       2.0,   # Wider — noisy, need more room
    'LOW_VOLATILE':  1.8,   # Wider — false breakout risk
    'BREAKOUT':      1.3,   # Tighter — breakouts should not retrace far
    'HIGH_VOLATILE': 2.5,   # Widest — but HIGH_VOLATILE blocks entry anyway
}

sl_multiplier = REGIME_SL_MULTIPLIERS[market_regime]
atr           = calculate_atr(df, period=14)
sl_distance   = atr × sl_multiplier

stop_loss_BUY  = entry_price - sl_distance
stop_loss_SELL = entry_price + sl_distance

# Minimum SL distance — never less than 0.5 ATR from entry
assert sl_distance >= atr × 0.5
```

### 3.2 Dynamic SL Tightening Triggers

Every management cycle (every 15 seconds), the bot evaluates these triggers. If any fires, the SL is moved to the tighter of: (a) the trigger-calculated level or (b) current SL. **SL never moves backward.**

| # | Trigger Condition | New SL Formula | Applies To | Priority |
|---|-------------------|----------------|------------|----------|
| 1 | RSI crosses back through 50 against trade direction | Price ∓ (ATR × 1.0) | BUY: RSI < 50 \| SELL: RSI > 50 | HIGH |
| 2 | MACD histogram flips against direction | Price ∓ (ATR × 0.8) | Any position in profit | HIGH |
| 3 | Price closes through EMA20 against direction | Price ∓ (ATR × 0.5) | Any position > 0.5 ATR in profit | MEDIUM |
| 4 | ADX drops below 20 (trend ending) | Price ∓ (ATR × 1.2) | Positions entered when ADX > 25 | MEDIUM |
| 5 | Bearish/Bullish engulfing candle against direction | Price ∓ (ATR × 0.7) | All positions | HIGH |
| 6 | Volume spike against direction (> 2× avg) | Price ∓ (ATR × 0.6) | All positions | MEDIUM |
| 7 | Upcoming HIGH impact event within 30 min | Closest round-number level within 1 ATR | All positions before blackout | HIGH |
| 8 | Daily max drawdown approaching (within 0.5%) | Price ∓ (ATR × 0.4) — emergency tighten | All positions | CRITICAL |

### 3.3 Breakeven Rules

Moving SL to breakeven protects capital once the trade has proven itself. These are **mandatory — not optional**.

| Condition | SL Moves To | Notes |
|-----------|-------------|-------|
| Price reaches 1.0 × ATR profit | Entry price + (0.1 × ATR) buffer | Covers spread and commission. Not exactly at entry — leaves small buffer. |
| T1 reaches TP1 (closed) | T2 SL moves to T1 entry price | T1 has banked profit. T2 now risks zero of original capital. |
| T2 reaches TP2 (closed) | T3 SL moves to T2 entry price | Only T3 runner remains. Entire original risk has been recovered. |
| Adverse news event announced | All positions SL → entry | Hard news protection. Do not wait for trigger — immediate move. |

---

## Section 04 — Adaptive Take Profit Management

*TP extends when trend accelerates — locks in when it stalls.*

Take Profit is not a fixed target. It adapts to momentum. When the trend is accelerating, TP is extended to capture more. When the trend stalls, TP is tightened or moved to a guaranteed partial exit.

### 4.1 Initial TP Calculation (Adaptive by Regime)

```python
# TP is calculated as a multiple of the SL distance (minimum R:R enforced)
TP_MULTIPLIERS = {
    'STRONG_TREND':  3.0,   # Ride it — trend has momentum
    'WEAK_TREND':    2.5,   # Standard
    'RANGING':       2.0,   # Minimum — mean reversion targets BB midline
    'LOW_VOLATILE':  2.2,   # Conservative
    'BREAKOUT':      3.5,   # Breakouts can run far
}

tp_multiplier = TP_MULTIPLIERS[market_regime]
tp_distance   = sl_distance × tp_multiplier

take_profit_BUY  = entry_price + tp_distance
take_profit_SELL = entry_price - tp_distance

# Hard minimum: R:R must always be >= 1.8 after any TP adjustment
rr = tp_distance / sl_distance
assert rr >= 1.8
```

### 4.2 TP Extension Triggers

When any of the following conditions are detected during the management cycle, the TP is extended. Each extension is logged with its trigger reason.

| # | Extension Trigger | Extension Amount | Condition / Guard |
|---|-------------------|-----------------|-------------------|
| 1 | ADX rose by ≥ 5 points since entry (trend accelerating) | + (ATR × 1.0) | ADX must be currently > 30. Only extend once per 5-point ADX increment. |
| 2 | Price momentum (ROC) > 0.5% in trade direction | + (ATR × 0.5) | Calculated over last 10 bars. Cap at 3 momentum extensions per trade. |
| 3 | Volume surge: current volume > 2.0× 20-bar average | + (ATR × 0.3) | Confirms institutional participation. Only 1 volume extension per trade. |
| 4 | Price hit original TP1 — close T1, extend T2 target | + (ATR × 1.5) on T2 | T1 closed at TP1. T2 now runs to TP2 extended target. |
| 5 | Strong trend candle: body > 1.5× ATR (momentum candle) | + (ATR × 0.4) | Next candle must also confirm direction. Revert extension if rejected. |
| 6 | MACD histogram expanding (each new high in histogram) | + (ATR × 0.3) | Only while histogram is making new highs. Reset when histogram contracts. |

### 4.3 TP Reduction / Early Exit Triggers

TP is tightened (moved closer) when the trend shows weakness. Once moved closer, TP **cannot be re-extended** in the same management session.

| Trigger | Action | Notes |
|---------|--------|-------|
| ADX drops below 25 AND was above 30 at entry | Move TP to 80% of remaining distance | Trend losing steam. Bank more of the profit. |
| RSI enters overbought/oversold zone against continuation | Move TP to next key S/R level | RSI > 75 on BUY or < 25 on SELL — exhaustion signal. |
| Price stalls: 3 consecutive candles with bodies < 0.3 ATR | Close 50% of T1 at market | Consolidation. Take partial profit rather than wait. |
| High-impact economic event within 60 minutes | Move all TP to nearest key level | Do not hold through high-impact events with open profit. |
| Opposing signal fires on same symbol (score ≥ 7.0) | Close all tranches at market | Strong counter-signal suggests reversal. Exit now. |

---

## Section 05 — Trailing Stop Rules

*Protect profit while staying in the trade.*

Trailing stops activate once a trade reaches **1.0 ATR in profit**. The trailing mode is selected by market regime. Trailing SL can only move in the profitable direction — never back.

### 5.1 Trailing Stop Activation

```python
# Activation threshold — must be in profit before trailing begins
profit_in_atr = (current_price - entry_price) / atr  # BUY
profit_in_atr = (entry_price - current_price) / atr  # SELL

if profit_in_atr >= 1.0 and not trailing_active:
    trailing_active = True
    log('TRAILING STOP ACTIVATED at profit = {:.2f} ATR'.format(profit_in_atr))

# Select mode by regime
TRAIL_MODE_BY_REGIME = {
    'STRONG_TREND':  'ATR',       # Stay in the trend
    'WEAK_TREND':    'STEP',      # Discrete steps — less whipsaw
    'RANGING':       'BREAKEVEN', # Just protect capital
    'BREAKOUT':      'ATR',       # Trail the breakout
    'LOW_VOLATILE':  'STEP',      # Conservative
}
```

### 5.2 Trailing Modes

| Mode | How It Works | Formula | Best Used When |
|------|-------------|---------|---------------|
| **ATR Trail** | SL follows peak price, always 1.5 ATR behind the high (BUY) or low (SELL). | `SL = peak_price ∓ (ATR × 1.5)` | Strong trends — STRONG_TREND, BREAKOUT regimes |
| **Step Trail** | SL advances in discrete 0.5 ATR steps as price makes new profit increments. | `SL = entry + (floor(profit/step) × step) ∓ ATR` | Weak trends — prevents whipsaw from micro-pullbacks |
| **Breakeven Trail** | Move SL to entry+buffer once 1 ATR in profit, then trail 1 ATR behind peak. | Phase 1: `SL = entry + 0.1×ATR` Phase 2: `SL = peak ∓ ATR` | Ranging markets — prioritise capital protection |
| **Parabolic SAR** | SL = Parabolic SAR value, which accelerates as trend extends. | `SL = psar(AF=0.02, max=0.2)` | Extended trends — T3 runner positions only |

### 5.3 Trailing Stop Rules

**RULE TR-01: Trailing SL only moves in the profitable direction**
BUY: new trail SL must be higher than current SL. SELL: new trail SL must be lower. If the formula gives a worse level, ignore it.

**RULE TR-02: Trailing activates at 1.0 ATR profit, not before**
Trailing too early causes premature exits on normal pullbacks. The first ATR of profit is protected by the static SL.

**RULE TR-03: T3 Runner uses Parabolic SAR only**
The T3 tranche is designed to ride the full trend. Parabolic SAR accelerates with the trend and only stops out when momentum reverses.

**RULE TR-04: Trailing gap cannot shrink below 0.5 ATR**
Minimum distance between current price and trailing SL is 0.5 ATR. Prevents stop-hunting on normal tick noise.

---

## Section 06 — Position Sizing & Risk Management

*Kelly Criterion with hard equity protection caps.*

### 6.1 Kelly Criterion Position Sizing

APEX uses **Half-Kelly** for all position sizing. Full Kelly is mathematically optimal but causes unacceptable drawdowns in practice. Half-Kelly preserves 75% of the growth rate while dramatically reducing variance.

```python
# Half-Kelly position sizing formula
win_rate      = historical_win_rate_for_strategy   # e.g. 0.58
avg_rr        = average_risk_reward_achieved       # e.g. 2.2

kelly_fraction = win_rate - ((1 - win_rate) / avg_rr)
half_kelly     = kelly_fraction × 0.5              # conservative

# Apply regime multiplier from AdaptiveRiskManager
risk_pct       = half_kelly × risk_multiplier

# Hard cap — never exceed MAX_RISK_PCT regardless of Kelly output
risk_pct       = min(risk_pct, MAX_RISK_PCT / 100)

# Dollar risk and lot size
risk_amount    = account_balance × risk_pct
lot_size       = risk_amount / (sl_distance × point_value)
lot_size       = round(min(lot_size, MAX_LOT_SIZE), 2)
```

### 6.2 Risk Multipliers by Market Regime

| Market Regime | Risk Multiplier | Effective Risk (at 1.5% base) | Rationale |
|---------------|----------------|-------------------------------|-----------|
| STRONG_TREND | 1.30× | 1.95% per trade | Ideal conditions — confidence justified |
| WEAK_TREND | 1.00× | 1.50% per trade | Normal conditions — standard sizing |
| RANGING | 0.70× | 1.05% per trade | Choppy market — reduce exposure |
| LOW_VOLATILE | 0.80× | 1.20% per trade | Low ATR = false breakout risk |
| BREAKOUT | 1.10× | 1.65% per trade | Breakout opportunity — slight increase |
| HIGH_VOLATILE | 0.50× | 0.75% per trade | Volatility spike — halve position |
| MACRO RISK_OFF | 0.60× | 0.90% per trade | Macro headwinds — reduce all positions |
| MACRO RISK_ON | 1.20× | 1.80% per trade | Macro tailwinds — slight increase allowed |

### 6.3 Hard Risk Limits — HARD VETO (Cannot Be Overridden)

| Limit | Threshold | Effect |
|-------|-----------|--------|
| Max risk per individual trade | **2.0% of account** | Hard cap. Kelly may suggest more — 2.0% is the ceiling. No exceptions. |
| Max combined open risk | **6.0% of account** | Sum of (lot × SL distance) across ALL open positions. No new positions if exceeded. |
| Max daily drawdown | **2.0% of account** | If daily loss hits 2%, bot stops trading for the calendar day. Resumes next day. |
| Max consecutive losses | **5 in a row** | After 5 consecutive losing trades, bot pauses for 4 hours and alerts operator. |
| Max open trades (same symbol) | **2 positions** | Prevents over-concentration (e.g. T1 + T2, no more). |
| Max open trades (total) | **10 positions** | Portfolio-level cap. Prevents over-leverage across all assets. |
| Min account equity to trade | **70% of starting capital** | If drawdown exceeds 30%, bot stops entirely and requires manual restart. |
| Single trade max lot size | **Config MAX_LOT_SIZE** | Absolute position cap regardless of balance or Kelly output. |

---

## Section 07 — Trade Exit Rules

*When and how to close positions.*

### 7.1 Normal Exit Hierarchy

Exits are evaluated in this priority order every management cycle. Higher priority exits override lower ones.

| Priority | Exit Type | Applies To | Trigger Condition |
|----------|-----------|------------|-------------------|
| P1 | Hard Stop Loss Hit | All tranches | Price touches or crosses the current SL level. Broker closes the position. |
| P2 | Hard Take Profit Hit | T1, T2, T3 independently | Price touches or crosses TP level for that tranche. Broker closes that tranche. |
| P3 | Emergency News Close | All tranches | HIGH impact event announced unexpectedly (not on calendar). Close all at market. |
| P4 | Opposing Signal Close | All tranches | A valid opposing signal fires with score ≥ 7.0 on the same symbol. |
| P5 | Daily Drawdown Limit | All tranches | Daily loss reaches MAX_DAILY_DRAWDOWN_PCT. Close all positions immediately. |
| P6 | SL Tightened to Near Price | All tranches | Dynamic SL has moved to within 0.2 ATR of price — effective exit. |
| P7 | Time-Based Exit (optional) | T1, T2 only | Position open > MAX_TRADE_DURATION with no profit. Exit to free capital. |
| P8 | Manual Override | Any tranche | Operator calls `POST /api/trades/{id}/close`. Immediate market close. |

### 7.2 Partial Profit Taking Rules

Partial exits lock in profit while keeping exposure to continue riding the trend. These rules apply to **T1 only** — T2 and T3 are managed by their own TP targets.

| Trigger | Close % of T1 | Action on Remainder |
|---------|--------------|---------------------|
| Price reaches 1.5 ATR profit (pre-TP1) | 25% of T1 at market | Move SL to entry. Let remaining 75% of T1 run to TP1. |
| Price stalls: 3 candles < 0.3 ATR body | 50% of T1 at market | Move SL to entry + 0.5 ATR. Trailing stop takes over. |
| High impact event within 60 minutes | 50% of T1 at market | Move SL to entry. Resume normal management post-event. |
| Session close approaching (21:00 UTC) | 100% of FX/Metal positions | Avoid overnight gaps on Forex and Gold. Crypto continues. |

---

## Section 08 — Correlation & Portfolio Rules

*Manage total exposure, not just individual trades.*

### 8.1 Correlated Asset Groups

Assets within the same group are treated as correlated. Opening the same direction on multiple assets in one group increases concentration risk.

| Group | Assets | Max Same-Direction Positions |
|-------|--------|------------------------------|
| USD Pairs | EURUSD, GBPUSD, AUDUSD, USDCHF, USDCAD, USDJPY | 2 positions max |
| Safe Havens | XAUUSD, XAGUSD, USDCHF, USDJPY (inverse) | 2 positions max |
| Risk Assets | S&P500, BTCUSD, ETHUSD, Oil | 2 positions max |
| Crypto | BTCUSD, ETHUSD, SOLUSD | 1 position max |
| Energy | USOIL, UK Brent, NATGAS | 2 positions max |

### 8.2 Portfolio-Level Rules

**RULE P-01: Check correlation before every new entry**
Before opening any position, calculate the directional exposure in its correlation group. Reject if the limit is exceeded.

**RULE P-02: Never hold opposing positions on the same symbol**
If a BUY and SELL signal both fire on XAUUSD, the stronger signal wins. Do not hedge on the same instrument.

**RULE P-03: Cap total open risk at 6% of account**
Sum all open `(lot × SL distance × point_value)`. If adding a new trade would exceed 6%, reject the signal regardless of quality.

**RULE P-04: Scale down during drawdown periods**
If the account is down more than 5% from its peak (drawdown mode), reduce all new position sizes by 50% until equity recovers.

---

## Section 09 — Session & Timing Rules

*Trade when liquidity is highest.*

| Asset Class | Preferred Session | Avoid | Notes |
|-------------|------------------|-------|-------|
| XAUUSD / Metals | London+NY overlap 08:00–17:00 UTC | Asian session 22:00–06:00 UTC | Highest liquidity 13:00–17:00 UTC. Most Gold moves happen then. |
| Forex Majors | London open 07:00–10:00 UTC, NY open 13:00–16:00 UTC | 21:00–23:00 UTC rollover | Avoid thin rollover window. Spreads widen significantly. |
| Crypto (BTC/ETH) | 24/7 — no restriction | No restriction | Monitor US market open (13:30 UTC) for correlation with equities. |
| Oil (WTI/Brent) | NY session 13:30–18:00 UTC | Before EIA inventory data (Wed 14:30 UTC) | EIA weekly crude inventory is a HIGH volatility event for oil. |
| US Indices (S&P) | NY open 13:30–15:30 UTC | Last 30 min of trading day | Volume drops sharply in final 30 minutes — avoid new entries. |

### 9.1 Calendar Blackout Windows

| Event Type | Block Before | Block After | Action During Blackout |
|------------|-------------|------------|------------------------|
| HIGH impact (NFP, FOMC, CPI) | 15 minutes | 30 minutes | Close all T1. Move T2/T3 SL to entry. No new entries. |
| MEDIUM impact | 5 minutes | 15 minutes | Tighten SL on all open positions by 0.5 ATR. No new entries. |
| LOW impact | None | None | Monitor only. Entries permitted. Watch for surprise deviation. |
| Central Bank speeches | 20 minutes | 20 minutes | Same as HIGH impact. Speeches cause sudden spikes. |
| Market open (major sessions) | 0 minutes | 5 minutes | Do not enter in first 5 minutes of session open — gap risk. |

---

## Section 10 — Management Cycle Checklist

*Every 15 seconds, in this exact order.*

The position manager runs this checklist for every open position on every cycle. Steps must execute in order — a failure at any step logs the error and skips to the next position (does not crash).

| Step | Action | Check / Calculation | On Failure |
|------|--------|---------------------|------------|
| 1 | **Verify Position** | Call `broker.get_open_trades()`. Confirm position ID exists in broker response. | If not found → position closed externally. Go to Step 9. |
| 2 | **Refresh Data** | Fetch last 200 OHLCV bars. Recalculate ATR, ADX, RSI, EMA20, MACD, BB, Volume. | Log warning. Skip this cycle. Do not modify position. |
| 3 | **Recalculate Conditions** | Run `AdaptiveRiskManager.analyse()`. Get fresh MarketConditions snapshot. | Use cached conditions from last successful cycle. |
| 4 | **Dynamic SL Check** | Evaluate all 8 SL tightening triggers (Section 3.2). Calculate candidate new SL. | No SL change if calculation fails. Log error. |
| 5 | **Dynamic TP Check** | Evaluate all 6 TP extension triggers (Section 4.2). Check 5 TP reduction triggers (Section 4.3). | No TP change if calculation fails. Log error. |
| 6 | **Trailing Stop** | If `trailing_active=True`, calculate new trail SL by active mode. Apply if it improves SL. | No change if trailing calc fails. Trailing stays at last known level. |
| 7 | **Apply Modifications** | If SL or TP changed: call `broker.modify_trade(sl=new_sl, tp=new_tp)`. Log all changes. | Retry once. If still fails, log CRITICAL and alert. |
| 8 | **Update Tracker** | Write updated SL, TP, current_price, unrealised_pnl to PositionTracker and DuckDB. | Log DB write error. In-memory state still valid. |
| 9 | **Detect Close** | If Step 1 found position missing: compute final P&L, write to `closed_trades` table, remove from tracker. | Always attempt close logging even if P&L calc fails. |
| 10 | **Tranche Trigger** | Check if conditions allow opening T2 or T3 (Section 2.1). If yes, queue signal. | Do not open tranches if main cycle failed. Safety check first. |

---

## Section 11 — Quick Reference Card

### Entry Gates Summary

| Parameter | Threshold |
|-----------|-----------|
| Min signal score | 6.5 / 10 |
| Min confidence | 60% |
| Min R:R ratio | 1.8 : 1 |
| Min ADX (momentum) | 18 |
| ATR ratio range | 0.5× – 2.0× |
| Volume threshold | ≥ 0.8× avg |

### Risk Limits Summary

| Parameter | Limit |
|-----------|-------|
| Max risk / trade | 2.0% |
| Max combined open risk | 6.0% |
| Max daily drawdown | 2.0% |
| Max consecutive losses | 5 |
| Max trades / symbol | 2 |
| Max total open trades | 10 |
| Min equity floor | 70% of peak |

### SL / TP Multipliers (× ATR)

| Regime | SL | TP (T1) | TP (T2) | TP (T3) |
|--------|-----|---------|---------|---------|
| STRONG_TREND | 1.2× | 2.0× | 3.5× | 5.5× |
| WEAK_TREND | 1.5× | 2.0× | 3.5× | 5.5× |
| RANGING | 2.0× | 2.0× | 3.5× | 5.5× |
| LOW_VOLATILE | 1.8× | 2.0× | 3.5× | 5.5× |
| BREAKOUT | 1.3× | 2.0× | 3.5× | 5.5× |

### Tranche Structure Summary

| | T1 — Anchor | T2 — Builder | T3 — Runner |
|--|------------|-------------|------------|
| **Lot size** | 40% | 35% | 25% |
| **Entry trigger** | Signal fires | T1 + 1.0 ATR profit | T1 + 2.0 ATR profit |
| **TP target** | 2.0× ATR | 3.5× ATR | 5.5× ATR |
| **Initial SL** | Regime × ATR | T1 entry price | T2 entry price |
| **Trailing mode** | None (static) | Step / ATR | Parabolic SAR |
| **Breakeven at** | 1.0× ATR profit | T1 closes | T2 closes |

### Indicator Reference

```python
# All indicators calculated on every management cycle
atr      = ATR(period=14)
adx      = ADX(period=14)          # trend strength
rsi      = RSI(period=14)          # momentum / exhaustion
ema20    = EMA(period=20)          # short-term trend
ema50    = EMA(period=50)          # medium-term trend
ema200   = EMA(period=200)         # long-term trend / HTF filter
macd     = MACD(12, 26, 9)        # momentum direction
bb       = BollingerBands(20, 2)   # volatility / squeeze
volume   = volume_ratio(period=20) # vs 20-bar average
psar     = ParabolicSAR(0.02, 0.2) # T3 trailing stop

# Regime classification thresholds
ADX > 35              → STRONG_TREND
ADX 20–35             → WEAK_TREND
ADX < 20              → RANGING
ATR_ratio > 2.0       → HIGH_VOLATILE (entry blocked)
ATR_ratio < 0.5       → LOW_VOLATILE
BB_squeeze + volume   → BREAKOUT
```

---

> **These rules are the bot's constitution. Every agent, strategy, and LLM decision operates within these boundaries.**
>
> *When in doubt, the bot does nothing. Preservation of capital always outranks pursuit of profit.*

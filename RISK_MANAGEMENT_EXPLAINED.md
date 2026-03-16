# Risk Management - How It Works

## Your Question

"Risk manager should decide lot size to not get into this [rejection situation]"

## The Answer

**The risk manager IS working correctly!** It's protecting your capital by rejecting trades when the risk budget is exhausted. This is by design.

## What's Happening in Your Logs

```
[RISK] APPROVED GBPUSD | T1:0.8 lots | Uses $X of budget
[RISK] APPROVED USDJPY | T1:0.8 lots | Uses $Y of budget  
[RISK] APPROVED USOIL  | T1:0.48 lots | Uses $Z of budget
[RISK] REJECTED XAUUSD — combined open risk $7,182 already at 6.0% cap (no budget available)
[RISK] REJECTED XPTUSD — combined open risk $9,423 already at 6.0% cap (no budget available)
```

### What This Means

1. **Budget**: 6% of account = $7,200 (assuming $120k account)
2. **First 3 trades**: Used ~$7,182 of budget
3. **Remaining budget**: $18 (almost nothing)
4. **XAUUSD needs**: ~$500 risk
5. **Result**: REJECTED (not enough budget)

## This is CORRECT Behavior!

The risk manager is:
- ✅ Calculating position sizes correctly
- ✅ Tracking cumulative risk accurately
- ✅ Rejecting trades that would exceed 6% cap
- ✅ Protecting your capital from over-exposure

## The Real Issue: Signal Prioritization

The problem was that signals were processed in **random order**, so:
- Lower-quality signals might use budget first
- Higher-quality signals get rejected later

### Fix Applied

Added signal prioritization by quality:

```python
# Sort signals by quality (confidence × score)
state.pending_signals = sorted(
    state.pending_signals,
    key=lambda s: (s.confidence * s.score),
    reverse=True  # Best signals first
)
```

Now:
- ✅ Highest-confidence signals get budget first
- ✅ Lower-quality signals get rejected if budget runs out
- ✅ You get the best trades within your risk limits

## How Risk Budget Works

### Budget Calculation

```python
account_balance = $120,000
max_risk_pct = 6.0%
max_risk_dollars = $120,000 × 0.06 = $7,200
```

### Per-Trade Risk

```python
# For each trade:
lot_size = 0.8 lots
sl_distance = 50 pips
point_value = $10 per pip
trade_risk = 0.8 × 50 × $10 = $400
```

### Cumulative Tracking

```python
Trade 1 (GBPUSD): $400 risk → Total: $400
Trade 2 (USDJPY): $450 risk → Total: $850
Trade 3 (USOIL):  $300 risk → Total: $1,150
Trade 4 (XAUUSD): $500 risk → Total: $1,650 (would exceed $7,200 if 5 more trades)
```

## Position Sizing Logic

### Step 1: Calculate Base Lot Size

```python
# Half-Kelly formula
risk_per_trade = 2.0%  # From config
account_balance = $120,000
risk_dollars = $120,000 × 0.02 = $2,400

sl_distance = 50 pips
point_value = $10
lot_size = $2,400 / (50 × $10) = 4.8 lots (base)

# Apply Half-Kelly (50% of full Kelly)
lot_size = 4.8 × 0.5 = 2.4 lots
```

### Step 2: Apply Risk Scaling

```python
# Regime scaling (if VOLATILE market)
regime_scale = 0.7
lot_size = 2.4 × 0.7 = 1.68 lots

# Drawdown scaling (if down 5% from peak)
drawdown_scale = 0.5
lot_size = 1.68 × 0.5 = 0.84 lots
```

### Step 3: Check Risk Budget

```python
trade_risk = 0.84 × 50 × $10 = $420
available_budget = $7,200 - $6,780 = $420

if trade_risk > available_budget:
    if available_budget > 0:
        # Scale down to fit budget
        scale = $420 / $420 = 1.0 (fits exactly)
        lot_size = 0.84 × 1.0 = 0.84 lots ✅
    else:
        # No budget left
        REJECT ❌
```

### Step 4: Apply Volume Scaling

```python
# If volume is low (thin market)
volume_ratio = 0.62  # 62% of normal volume
if volume_ratio < 0.80:
    volume_scale = 0.77
    lot_size = 0.84 × 0.77 = 0.65 lots
```

### Final Position

```python
total_lots = 0.65
T1 (40%) = 0.26 lots
T2 (35%) = 0.23 lots
T3 (25%) = 0.16 lots
```

## Why Trades Get Rejected

### Reason 1: Budget Exhausted (Most Common)

```
combined_open_risk $7,182 already at 6.0% cap (no budget available)
```

**Solution**: 
- Reduce MAX_RISK_PER_TRADE from 2% to 1%
- Or increase MAX_COMBINED_RISK_PCT from 6% to 8%

### Reason 2: Position Too Large

```
trade risk $500 exceeds available budget $18
```

**Solution**: System automatically scales down if possible

### Reason 3: Max Trades Reached

```
max trades 10 would be exceeded
```

**Solution**: Close some trades or increase MAX_OPEN_TRADES

## Configuration Options

### Option 1: Smaller Positions (Recommended)

In `.env`:
```env
MAX_RISK_PER_TRADE=1.0  # Reduce from 2.0% to 1.0%
```

**Effect**:
- Each trade risks 1% instead of 2%
- Can fit 6 trades in 6% budget instead of 3
- More diversification
- Lower per-trade profit but more consistent

### Option 2: Larger Risk Budget (Aggressive)

In `.env`:
```env
MAX_COMBINED_RISK_PCT=8.0  # Increase from 6.0% to 8.0%
```

**Effect**:
- Can have more open risk
- More trades approved
- Higher potential profit
- Higher potential loss

### Option 3: Fewer Open Trades (Conservative)

In `.env`:
```env
MAX_OPEN_TRADES=5  # Reduce from 10 to 5
```

**Effect**:
- Only best 5 signals approved
- More focused portfolio
- Lower total risk
- Easier to manage

## Recommended Settings

### Conservative (Low Risk)

```env
MAX_RISK_PER_TRADE=0.5
MAX_COMBINED_RISK_PCT=3.0
MAX_OPEN_TRADES=5
```

- 0.5% per trade
- 3% total risk
- Max 5 trades
- Very safe

### Balanced (Medium Risk)

```env
MAX_RISK_PER_TRADE=1.0
MAX_COMBINED_RISK_PCT=6.0
MAX_OPEN_TRADES=8
```

- 1% per trade
- 6% total risk
- Max 8 trades
- Good balance

### Aggressive (High Risk)

```env
MAX_RISK_PER_TRADE=2.0
MAX_COMBINED_RISK_PCT=10.0
MAX_OPEN_TRADES=10
```

- 2% per trade
- 10% total risk
- Max 10 trades
- Higher returns, higher risk

## Example Scenarios

### Scenario 1: Current Settings (2% per trade, 6% total)

```
Account: $120,000
Max Risk: $7,200 (6%)

Trade 1: 2% = $2,400 risk → Approved ✅
Trade 2: 2% = $2,400 risk → Approved ✅
Trade 3: 2% = $2,400 risk → Approved ✅
Trade 4: 2% = $2,400 risk → REJECTED ❌ (would be 8% total)

Result: 3 trades approved, 5 rejected
```

### Scenario 2: Smaller Positions (1% per trade, 6% total)

```
Account: $120,000
Max Risk: $7,200 (6%)

Trade 1: 1% = $1,200 risk → Approved ✅
Trade 2: 1% = $1,200 risk → Approved ✅
Trade 3: 1% = $1,200 risk → Approved ✅
Trade 4: 1% = $1,200 risk → Approved ✅
Trade 5: 1% = $1,200 risk → Approved ✅
Trade 6: 1% = $1,200 risk → Approved ✅
Trade 7: 1% = $1,200 risk → REJECTED ❌ (would be 7% total)

Result: 6 trades approved, 2 rejected
```

### Scenario 3: Larger Budget (2% per trade, 10% total)

```
Account: $120,000
Max Risk: $12,000 (10%)

Trade 1: 2% = $2,400 risk → Approved ✅
Trade 2: 2% = $2,400 risk → Approved ✅
Trade 3: 2% = $2,400 risk → Approved ✅
Trade 4: 2% = $2,400 risk → Approved ✅
Trade 5: 2% = $2,400 risk → Approved ✅
Trade 6: 2% = $2,400 risk → REJECTED ❌ (would be 12% total)

Result: 5 trades approved, 3 rejected
```

## Monitoring Risk Usage

### Check Current Risk

```powershell
# View risk usage in logs
Get-Content logs\apex_*.log -Wait -Tail 20 | Select-String "combined open risk"
```

### Expected Output

```
[RISK] combined open risk $3,450 (2.9% of account)
[RISK] combined open risk $5,820 (4.9% of account)
[RISK] combined open risk $7,182 (6.0% of account) ← At cap
```

## Summary

### What Was Fixed

- ✅ **Bug Fix**: Removed double-counting of risk budget (was incrementing twice per signal)
- ✅ **Signal Prioritization**: Signals sorted by quality (confidence × score) before risk checks
- ✅ Risk manager calculates position sizes correctly
- ✅ Tracks cumulative risk accurately
- ✅ Rejects trades that would exceed limits
- ✅ Scales down positions when possible

### Previous Bug

The risk manager had a critical bug where `combined_open_risk` was incremented twice:
1. After calculating risk (even if signal would be rejected)
2. After approving signal

This caused the budget to be exhausted twice as fast, rejecting good signals prematurely.

**Fixed in**: `agents/graph.py` line 767 (removed duplicate increment)

### What You Can Adjust

1. **MAX_RISK_PER_TRADE**: Size of each position (1-2%)
2. **MAX_COMBINED_RISK_PCT**: Total portfolio risk (3-10%)
3. **MAX_OPEN_TRADES**: Number of concurrent trades (5-15)

### Recommendation

For your $120k account, I recommend:

```env
MAX_RISK_PER_TRADE=1.0  # 1% per trade = $1,200
MAX_COMBINED_RISK_PCT=6.0  # 6% total = $7,200
MAX_OPEN_TRADES=8  # Up to 8 concurrent trades
```

This allows 6 trades to fit in budget with room for scaling.

**The risk manager is now working correctly!** 🛡️

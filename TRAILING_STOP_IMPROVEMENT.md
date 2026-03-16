# Trailing Stop Loss - Improvement Strategy

## Problem Analysis

Trades were in profit but closed at loss because the trailing stop wasn't protecting gains aggressively enough.

### Current Issues

1. **Late Activation**: Trailing only starts at 1.0 ATR profit
2. **Wide Trail Distance**: 1.5 ATR from peak allows too much retracement
3. **Slow Step Mode**: Only moves every 0.5 ATR
4. **No Profit Protection Zones**: Same trail distance regardless of profit level

## Root Cause

When a trade moves into profit, the current system:
- Waits for 1.0 ATR profit before trailing
- Allows 1.5 ATR retracement from peak
- Result: A trade at +2.0 ATR can retrace -1.5 ATR and still be open, ending at +0.5 ATR or worse

### Example Scenario
```
Entry: 2000.00
Peak:  2020.00 (+2.0 ATR, ATR=10)
Trail SL: 2020 - 15 = 2005.00
Price retraces to: 2004.00
SL Hit at: 2005.00
Result: +0.5 ATR profit instead of +2.0 ATR
```

## Proposed Solution: Tiered Trailing Stop

### Concept
Use **tighter trail distances** as profit increases, protecting more gains at higher profit levels.

### Profit Zones

| Profit Level | Trail Distance | Protection | Rationale |
|--------------|----------------|------------|-----------|
| 0.0 - 0.5 ATR | No trailing | Initial SL | Let trade breathe |
| 0.5 - 1.0 ATR | 1.0 ATR | 50% protection | Early profit, cautious |
| 1.0 - 2.0 ATR | 0.75 ATR | 62.5% protection | Good profit, tighten |
| 2.0 - 3.0 ATR | 0.5 ATR | 75% protection | Strong profit, aggressive |
| 3.0+ ATR | 0.3 ATR | 90% protection | Exceptional, lock in |

### Activation Threshold
- **Current**: 1.0 ATR
- **Proposed**: 0.5 ATR (earlier protection)

### Trail Modes by Regime

#### STRONG_TREND
- Use ATR mode with tiered distances
- Allow more room for continuation
- Trail distance: 0.75 ATR at 1.0 ATR profit

#### WEAK_TREND
- Use STEP mode with tighter steps
- Move SL every 0.3 ATR instead of 0.5 ATR
- More conservative protection

#### RANGING
- Use BREAKEVEN mode
- Move to breakeven at 0.5 ATR profit
- Trail at 0.5 ATR from peak after 1.0 ATR profit

#### HIGH_VOLATILE
- Use wider trail distance (1.0 ATR)
- Avoid premature stops from noise
- But still activate at 0.5 ATR profit

## Implementation

### New Tiered Trail Function

```python
def _compute_tiered_trail_sl(ps: _PositionState, ind: dict[str, float]) -> float | None:
    """
    Tiered trailing stop - tighter protection as profit increases.
    """
    price = ind.get("price", ps.entry_price)
    atr = ind.get("atr", ps.atr) or ps.atr or 1.0
    buy = _is_buy(ps.direction)
    
    # Update peak
    if buy:
        ps.peak_price = max(ps.peak_price, price)
    else:
        ps.peak_price = min(ps.peak_price, price)
    
    profit_atr = _profit_in_atr(ps, price)
    
    # Activation at 0.5 ATR (earlier than before)
    if not ps.trailing_active:
        if profit_atr >= 0.5:
            ps.trailing_active = True
            log.info("[POSMGR] {} Trailing ACTIVATED at {:.2f} ATR profit", 
                    ps.symbol, profit_atr)
        else:
            return None
    
    # Determine trail distance based on profit level
    if profit_atr >= 3.0:
        trail_dist = 0.3  # Lock in 90% of gains
    elif profit_atr >= 2.0:
        trail_dist = 0.5  # Lock in 75% of gains
    elif profit_atr >= 1.0:
        trail_dist = 0.75  # Lock in 62.5% of gains
    else:
        trail_dist = 1.0  # Lock in 50% of gains
    
    # Adjust for regime
    regime = ps.regime
    if regime == "HIGH_VOLATILE":
        trail_dist *= 1.3  # Wider for volatile markets
    elif regime == "STRONG_TREND":
        trail_dist *= 1.1  # Slightly wider for trends
    elif regime == "RANGING":
        trail_dist *= 0.8  # Tighter for ranging
    
    # Calculate new SL from peak
    new_sl = ps.peak_price - (atr * trail_dist) if buy else ps.peak_price + (atr * trail_dist)
    
    # Minimum gap from current price (0.3 ATR)
    min_gap = atr * 0.3
    if buy and price - new_sl < min_gap:
        new_sl = price - min_gap
    elif not buy and new_sl - price < min_gap:
        new_sl = price + min_gap
    
    # SL only moves in profitable direction
    if buy and new_sl <= ps.current_sl:
        return None
    if not buy and new_sl >= ps.current_sl:
        return None
    
    return new_sl
```

### Breakeven Protection

```python
def _check_breakeven_aggressive(ps: _PositionState, price: float) -> float | None:
    """
    Move to breakeven earlier and more aggressively.
    """
    atr = ps.atr or 1.0
    buy = _is_buy(ps.direction)
    profit_atr = _profit_in_atr(ps, price)
    
    # Move to breakeven at 0.5 ATR profit (was 1.0 ATR)
    if profit_atr >= 0.5 and not ps.breakeven_set:
        ps.breakeven_set = True
        # Add small buffer (0.05 ATR) to avoid spread issues
        buffer = atr * 0.05
        return (ps.entry_price + buffer) if buy else (ps.entry_price - buffer)
    
    return None
```

## Configuration Changes

### Update `core/config.py`

```python
# Trailing Stop Configuration
TRAILING_ACTIVATION_ATR = 0.5  # Was 1.0
TRAILING_MIN_GAP_ATR = 0.3     # Was 0.5

# Tiered Trail Distances
TRAIL_DISTANCE_TIERS = {
    "0.5-1.0": 1.0,   # 50% protection
    "1.0-2.0": 0.75,  # 62.5% protection
    "2.0-3.0": 0.5,   # 75% protection
    "3.0+": 0.3,      # 90% protection
}

# Regime Multipliers for Trail Distance
REGIME_TRAIL_MULTIPLIERS = {
    "STRONG_TREND": 1.1,
    "WEAK_TREND": 1.0,
    "RANGING": 0.8,
    "HIGH_VOLATILE": 1.3,
    "LOW_VOLATILE": 0.9,
}
```

## Testing Strategy

### Backtest Scenarios

1. **Strong Trend**: Trade moves +3.0 ATR then retraces
   - Old: SL at entry + 1.5 ATR = +1.5 ATR profit
   - New: SL at peak - 0.3 ATR = +2.7 ATR profit

2. **Choppy Market**: Trade moves +1.5 ATR, retraces, moves again
   - Old: May get stopped out at +0.5 ATR
   - New: Breakeven at +0.5 ATR, protected

3. **False Breakout**: Trade moves +0.8 ATR then reverses
   - Old: No trailing, hits original SL
   - New: Trailing active, SL at entry + 0.3 ATR

### Performance Metrics

Track these metrics before/after:
- Average profit per winning trade
- Profit giveback percentage
- Win rate (should stay same or improve)
- Average R:R (should improve)

## Implementation Steps

1. **Add tiered trail function** to `utils/position_manager.py`
2. **Update config** with new thresholds
3. **Replace** `_compute_trail_sl()` call with `_compute_tiered_trail_sl()`
4. **Update** `_check_breakeven()` to be more aggressive
5. **Test** on paper trading for 1 week
6. **Monitor** profit giveback metrics
7. **Adjust** tier thresholds based on results

## Expected Results

### Before (Current System)
- Activation: 1.0 ATR
- Trail distance: 1.5 ATR
- Profit giveback: 50-75%
- Example: +2.0 ATR → closes at +0.5 ATR

### After (Tiered System)
- Activation: 0.5 ATR
- Trail distance: 0.3-1.0 ATR (tiered)
- Profit giveback: 10-25%
- Example: +2.0 ATR → closes at +1.5 ATR

## Risk Considerations

### Potential Issues
1. **Premature stops**: Tighter trailing may stop out trends early
2. **Whipsaw**: More stops in choppy markets
3. **Spread sensitivity**: Tighter SL more affected by spread

### Mitigations
1. **Regime-based adjustments**: Wider trails in STRONG_TREND
2. **Minimum gap**: 0.3 ATR prevents too-tight SL
3. **Activation threshold**: 0.5 ATR ensures some profit before trailing

## Alternative: Chandelier Stop

Consider using Chandelier Stop as alternative:
```python
def _chandelier_stop(ps: _PositionState, ind: dict[str, float]) -> float | None:
    """
    Chandelier Stop: SL = Highest High - (ATR × multiplier)
    """
    atr = ind.get("atr", ps.atr) or ps.atr or 1.0
    multiplier = 2.0  # Adjust based on profit level
    
    if profit_atr >= 2.0:
        multiplier = 1.0  # Tighter at high profit
    
    if _is_buy(ps.direction):
        return ps.peak_price - (atr * multiplier)
    else:
        return ps.peak_price + (atr * multiplier)
```

## Monitoring Dashboard

Add to dashboard:
- Trail activation count
- Average profit at trail activation
- Average profit at close
- Profit giveback percentage
- Trail mode distribution

## Conclusion

The tiered trailing stop system provides:
1. **Earlier protection**: Activates at 0.5 ATR
2. **Progressive tightening**: Locks in more profit as trade develops
3. **Regime awareness**: Adjusts for market conditions
4. **Reduced giveback**: Protects 75-90% of peak profit

This should significantly reduce the issue of profitable trades closing at loss.

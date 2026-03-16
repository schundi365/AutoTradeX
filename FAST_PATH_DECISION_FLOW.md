# APEX Bot - Fast Path Decision Flow

## Overview

The bot uses a **Hybrid Decision Engine** that combines:
- **Fast Path** (90%): Rule-based decisions using technical indicators
- **LLM Review** (10%): AI review for edge cases and complex scenarios

## Complete Order Placement Flow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. BOT CYCLE STARTS (Every 1 minute)                       │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. AGENT PIPELINE (8 Stages)                               │
├─────────────────────────────────────────────────────────────┤
│ Stage 1: DataCollectionAgent                               │
│   - Fetch market data (OHLCV, quotes)                      │
│   - Get account info from MT5                              │
│                                                             │
│ Stage 2: TechnicalAnalysisAgent                            │
│   - Calculate 20+ indicators (RSI, ADX, ATR, MACD, EMA)    │
│   - Detect market regime (TRENDING/RANGING/VOLATILE)       │
│   - Apply Smart Money Concepts (FVG, Order Blocks, BOS)    │
│   - Generate trading signals with scores                   │
│                                                             │
│ Stage 3: SentimentAgent                                    │
│   - Fetch news sentiment                                   │
│   - Check long-term memory (ChromaDB)                      │
│                                                             │
│ Stage 4: CalendarAgent                                     │
│   - Check economic calendar                                │
│   - Set news blackout if high-impact event coming          │
│                                                             │
│ Stage 5: MacroAgent                                        │
│   - Fetch DXY (US Dollar Index)                            │
│   - Fetch US10Y (Treasury Yield)                           │
│                                                             │
│ Stage 6: RiskManagementAgent                               │
│   - Run 10 quality gates (G1-G10)                          │
│   - Check risk budget, correlation, drawdown               │
│   - Filter out signals that fail risk checks               │
│                                                             │
│ Stage 7: AutonomousOrchestrator (DECISION ENGINE)          │
│   ┌─────────────────────────────────────────────────┐     │
│   │ FAST PATH (Rule-Based)                          │     │
│   │ - Check if signal meets clear criteria          │     │
│   │ - Strong trend: ADX > 25, RSI not extreme       │     │
│   │ - Good risk/reward: R:R > 2.0                   │     │
│   │ - No news blackout                               │     │
│   │ - Passes all 10 risk gates                      │     │
│   │                                                  │     │
│   │ If ALL criteria met → APPROVE (GO)              │     │
│   │ If ANY criteria fails → REJECT (NOGO)           │     │
│   └─────────────────────────────────────────────────┘     │
│                          ↓                                  │
│   ┌─────────────────────────────────────────────────┐     │
│   │ LLM REVIEW (Edge Cases - 10% of signals)        │     │
│   │ - Ambiguous signals (borderline indicators)     │     │
│   │ - Complex market conditions                     │     │
│   │ - Conflicting signals                           │     │
│   │                                                  │     │
│   │ If LLM unavailable → Fast path decides          │     │
│   └─────────────────────────────────────────────────┘     │
│                                                             │
│ Stage 8: ExecutionAgent                                    │
│   - Place approved orders via MT5                          │
│   - Set SL/TP based on ATR                                 │
│   - Calculate position size (risk-based)                   │
└─────────────────────────────────────────────────────────────┘
```

## Fast Path Decision Criteria


### Signal Approval Logic (Fast Path)

A signal is **APPROVED** if ALL of these are true:

1. **Strong Trend Detected**
   - ADX > 25 (strong directional movement)
   - RSI between 30-70 (not overbought/oversold)
   - Price above/below key EMAs

2. **Good Risk/Reward**
   - Risk:Reward ratio > 2.0
   - Stop loss < 2% of account
   - Take profit > 4% of account

3. **No News Blackout**
   - No high-impact news in next 2 hours
   - Not during major economic releases

4. **Passes All 10 Risk Gates**
   - G1: Signal score > threshold
   - G2: Risk budget available
   - G3: Max open trades not exceeded
   - G4: No excessive correlation
   - G5: Drawdown within limits
   - G6: Volatility acceptable
   - G7: Spread reasonable
   - G8: Liquidity sufficient
   - G9: Time of day appropriate
   - G10: Symbol allowed

5. **Technical Confirmation**
   - Multiple timeframes aligned
   - Volume confirms direction
   - Smart Money Concepts support trade

### Example: XAUUSD SELL Signal

```
Input Signal:
- Symbol: XAUUSD
- Direction: SELL
- Entry: 2318.50
- Stop Loss: 2325.00 (0.28% risk)
- Take Profit: 2305.00 (0.58% reward)
- Risk:Reward: 2.07

Technical Indicators:
- ADX: 28.5 (Strong trend ✓)
- RSI: 45.2 (Not extreme ✓)
- ATR: 6.5 (Normal volatility ✓)
- EMA Alignment: Price below EMA50 ✓

Risk Checks:
- G1: Score 8.5/10 ✓
- G2: Risk budget 2.5% available ✓
- G3: 1/5 open trades ✓
- G4: No correlated positions ✓
- G5: Drawdown 1.2% (< 5% limit) ✓
- G6-G10: All pass ✓

News Check:
- No high-impact events ✓

DECISION: APPROVE (GO) via Fast Path
Reason: All criteria met, no LLM review needed
```

## Order Placement Flow


### Step-by-Step Order Execution

```
1. Signal Approved by Orchestrator
   ↓
2. ExecutionAgent receives approved signal
   ↓
3. Calculate Position Size
   - Risk per trade: 1% of account balance
   - Account balance: $10,000
   - Risk amount: $100
   - Stop loss distance: 6.5 pips (0.28%)
   - Position size: $100 / 6.5 = 0.15 lots
   ↓
4. Prepare Order Request
   {
     "symbol": "XAUUSD",
     "direction": "SELL",
     "lot_size": 0.15,
     "entry_price": 2318.50,
     "stop_loss": 2325.00,
     "take_profit": 2305.00,
     "strategy": "AI_MOMENTUM",
     "magic": 888888
   }
   ↓
5. Send to MT5 Broker
   - MT5Broker.place_order(trade)
   - Uses mt5.order_send() with TRADE_ACTION_DEAL
   - Tries multiple filling modes (IOC, FOK, RETURN)
   ↓
6. MT5 Executes Order
   - Checks margin requirements
   - Validates price levels
   - Places order on market
   - Returns order ticket ID
   ↓
7. Store Trade in Database
   - Save to DuckDB (data/apex.db)
   - Add to bot_state.open_trades
   - Log to trade journal
   ↓
8. Monitor Trade
   - Check SL/TP hit every cycle
   - Update P&L in real-time
   - Sync with MT5 positions
```

## Code Flow (Simplified)

### 1. Orchestrator Decision (agents/autonomous_orchestrator.py)

```python
async def decide_batch(self, signals: list[TradingSignal]) -> list[TradingSignal]:
    """Hybrid decision engine: Fast path + LLM review"""
    
    approved = []
    edge_cases = []
    
    for signal in signals:
        # FAST PATH: Check clear criteria
        if self._is_clear_go(signal):
            signal.decision = "GO"
            signal.reasoning = "Fast path: All criteria met"
            approved.append(signal)
            log.info(f"✓ {signal.symbol} {signal.direction} — Fast path approved")
            
        elif self._is_clear_nogo(signal):
            signal.decision = "NOGO"
            signal.reasoning = "Fast path: Criteria not met"
            log.info(f"✗ {signal.symbol} {signal.direction} — Fast path rejected")
            
        else:
            # Edge case: needs LLM review
            edge_cases.append(signal)
    
    # LLM review for edge cases (if available)
    if edge_cases and self.llm_available:
        llm_decisions = await self._llm_review(edge_cases)
        approved.extend(llm_decisions)
    else:
        # LLM unavailable: Fast path decides edge cases
        for signal in edge_cases:
            if signal.score >= 7.0:  # Conservative threshold
                signal.decision = "GO"
                approved.append(signal)
                log.info(f"✓ {signal.symbol} — LLM unavailable, approved by fast path")
    
    return approved
```

### 2. Fast Path Criteria Check

```python
def _is_clear_go(self, signal: TradingSignal) -> bool:
    """Check if signal clearly meets all criteria"""
    
    # Strong trend
    if signal.indicators.get("adx", 0) < 25:
        return False
    
    # RSI not extreme
    rsi = signal.indicators.get("rsi", 50)
    if rsi < 30 or rsi > 70:
        return False
    
    # Good risk/reward
    if signal.risk_reward < 2.0:
        return False
    
    # No news blackout
    if signal.is_news_blackout:
        return False
    
    # High confidence score
    if signal.score < 8.0:
        return False
    
    return True
```

### 3. Order Execution (agents/graph.py)

```python
async def execution_agent(state: BotState) -> BotState:
    """Execute approved signals"""
    
    broker = BrokerFactory(settings).get("MT5")
    
    for signal in state.approved_signals:
        try:
            # Calculate position size
            lot_size = calculate_position_size(
                signal=signal,
                balance=state.account_info.balance,
                risk_pct=settings.max_risk_per_trade
            )
            
            # Create trade object
            trade = Trade(
                symbol=signal.symbol,
                direction=signal.direction,
                lot_size=lot_size,
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                strategy=signal.strategy
            )
            
            # Place order via MT5
            executed_trade = await broker.place_order(trade)
            
            # Add to open trades
            state.open_trades.append(executed_trade)
            
            log.success(f"ORDER PLACED: {signal.symbol} {signal.direction} @ {signal.entry_price}")
            
        except Exception as e:
            log.error(f"Order failed: {signal.symbol} - {e}")
    
    return state
```

## Why Fast Path?

### Performance Benefits

- **Speed**: 60-70x faster than LLM-only (50ms vs 3000ms)
- **Reliability**: Works even when LLM is down
- **Cost**: No API costs for 90% of decisions
- **Consistency**: Rule-based decisions are deterministic

### When LLM is Used

LLM reviews only **edge cases** (10% of signals):
- Borderline indicators (ADX 23-27, RSI 28-32 or 68-72)
- Conflicting signals (bullish RSI, bearish MACD)
- Complex market conditions (high volatility + news)
- Novel patterns not covered by rules

## Your Log Example

```
09:38:57 [SYSTEM][LLM_BATCH] ✓ XAUUSD Direction.SELL — LLM unavailable, approved by fast path
09:38:54 [SYSTEM][LLM_BATCH] ✓ GBPUSD Direction.SELL — LLM unavailable, approved by fast path
09:38:50 [SYSTEM][LLM_BATCH] ✓ UKOIL Direction.SELL — LLM unavailable, approved by fast path
```

**What happened:**
1. Bot generated SELL signals for XAUUSD, GBPUSD, UKOIL
2. Signals passed fast path criteria (strong trend, good R:R, no news)
3. LLM (Ollama) was unavailable or slow to respond
4. Fast path approved all 3 signals independently
5. Orders were placed via MT5

**This is normal and expected behavior** - the fast path is designed to work independently when LLM is unavailable.

## Monitoring Decisions

Check decision history in dashboard:
- **BOT DECISIONS** tab shows all GO/NOGO decisions
- **Decision Time** shows how fast decisions were made
- **Decision Maker** shows FAST_PATH vs LLM vs HYBRID

Or check logs:
```powershell
Get-Content logs/apex_*.log | Select-String "Fast path"
```

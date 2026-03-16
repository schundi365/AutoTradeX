# Decision Tracing Guide

## Overview

The Decision Tracing system provides complete visibility into every trading decision made by the APEX bot. It captures:

- **Every step** of the decision-making process
- **Agent-level logs** from each component
- **Input/output data** at each step
- **Reasoning** behind each decision
- **Why trades were accepted or rejected**
- **Complete execution timeline** with millisecond precision

---

## Features

### 1. Complete Decision Capture
- Multi-step decision process tracking
- Agent-specific logging
- Input/output data capture
- Reasoning documentation
- Performance metrics (duration per step)

### 2. Decision Trace Viewer Dashboard
**Location:** `/trace` in the dashboard

- **Real-time trace list** - See all recent decisions
- **Detailed step-by-step view** - Expand each step to see logs and data
- **Filtering** - By decision type, symbol, or search term
- **Agent logs** - See exactly what each agent logged
- **Market state snapshot** - Market conditions at decision time

### 3. Integration with Existing Systems
- Works with FastDecisionEngine
- Compatible with MacroAgent and AutonomousOrchestrator
- Integrates with Trade Journal
- Links to Performance Analytics

---

## Dashboard Usage

### Viewing Decision Traces

1. **Navigate to Decision Trace** (`/trace`)
2. **Filter traces:**
   - Select decision type (TRADE_OPENED, TRADE_REJECTED, etc.)
   - Select symbol (XAUUSD, EURUSD, etc.)
   - Search by ID or symbol
3. **Click on a trace** to view details
4. **Expand steps** to see:
   - Agent logs
   - Input data
   - Output data
   - Reasoning
   - Duration

### Understanding Decision Steps

Each decision typically includes these steps:

1. **Signal Generation**
   - Agent: FastDecisionEngine
   - Calculates signal score
   - Checks against threshold
   - Status: PASSED/FAILED

2. **Risk Management Check**
   - Agent: RiskManager
   - Validates risk limits
   - Checks position limits
   - Status: PASSED/FAILED/SKIPPED

3. **Position Sizing**
   - Agent: PositionSizer
   - Calculates lot size
   - Sets stop loss and take profit
   - Status: PASSED

4. **ML Model Prediction** (Optional)
   - Agent: ModelInferenceService
   - Gets model prediction
   - Adds confidence score
   - Status: PASSED/SKIPPED

5. **Final Decision**
   - Agent: FastDecisionEngine
   - Makes final call
   - Executes or rejects trade
   - Status: PASSED/FAILED

### Decision Types

- **TRADE_OPENED** - Trade was executed
- **TRADE_REJECTED** - Trade was rejected (see rejection_reason)
- **TRADE_CLOSED** - Position was closed
- **POSITION_ADJUSTED** - Stop loss or take profit adjusted

### Step Status

- **PASSED** (✓ green) - Step completed successfully
- **FAILED** (✗ red) - Step failed, decision rejected
- **SKIPPED** (○ gray) - Step skipped (e.g., no ML model)

---

## Code Integration

### Basic Usage

```python
from core.decision_tracer import DecisionTracer, DecisionType

# Create tracer
tracer = DecisionTracer(
    symbol="XAUUSD",
    market_state={"price": 2050.0, "regime": "STRONG_TREND"}
)

# Add decision steps
with tracer.step("Signal Generation", "FastDecisionEngine") as step:
    step.log("INFO", "Calculating signal score")
    step.set_input({"price": 2050.0})
    
    signal_score = calculate_signal()
    
    step.set_output({"signal_score": signal_score})
    step.set_reasoning("Signal score above threshold")
    
    if signal_score < threshold:
        step.fail("Signal too weak")

# Finalize trace
tracer.finalize(
    decision_type=DecisionType.TRADE_OPENED,
    final_decision="LONG 0.5 lots",
    confidence=85.0
)
```

### Step Context Methods

```python
with tracer.step("Step Name", "AgentName") as step:
    # Log messages
    step.log("INFO", "Processing...")
    step.log("DEBUG", "Details", context={"key": "value"})
    step.log("WARNING", "Potential issue")
    step.log("ERROR", "Failed")
    
    # Set input data
    step.set_input({"param1": value1, "param2": value2})
    
    # Set output data
    step.set_output({"result": result_value})
    
    # Set reasoning
    step.set_reasoning("Why this decision was made")
    
    # Mark as failed
    step.fail("Reason for failure")
    
    # Mark as skipped
    step.skip("Reason for skipping")
```

### Integration with FastDecisionEngine

```python
class FastDecisionEngine:
    def evaluate(self, symbol: str):
        # Get market state
        market_state = self.market_context.get_state(symbol)
        
        # Create tracer
        tracer = DecisionTracer(symbol=symbol, market_state=market_state)
        
        # Step 1: Signal calculation
        with tracer.step("Signal Calculation", "FastDecisionEngine") as step:
            step.log("INFO", f"Evaluating {symbol}")
            signal_score = self._calculate_signal(symbol)
            step.set_output({"signal_score": signal_score})
            
            if signal_score < self.config.min_signal_score:
                step.fail(f"Signal {signal_score} below threshold")
                tracer.finalize(
                    decision_type=DecisionType.TRADE_REJECTED,
                    final_decision="No trade",
                    confidence=0.0,
                    rejection_reason=f"Signal score {signal_score} below threshold"
                )
                return None
        
        # Step 2: Risk checks
        with tracer.step("Risk Checks", "RiskManager") as step:
            risk_ok = self._check_risk_limits(symbol)
            if not risk_ok:
                step.fail("Risk limits exceeded")
                tracer.finalize(
                    decision_type=DecisionType.TRADE_REJECTED,
                    final_decision="No trade",
                    confidence=0.0,
                    rejection_reason="Risk limits exceeded"
                )
                return None
        
        # Step 3: Execute trade
        with tracer.step("Trade Execution", "FastDecisionEngine") as step:
            trade = self._execute_trade(symbol)
            tracer.finalize(
                decision_type=DecisionType.TRADE_OPENED,
                final_decision=f"{trade.direction} {trade.lot_size} lots",
                confidence=signal_score * 10
            )
            return trade
```

### Integration with MacroAgent

```python
class MacroAgent:
    def analyze_opportunity(self, symbol: str):
        tracer = DecisionTracer(symbol=symbol)
        
        with tracer.step("Macro Analysis", "MacroAgent") as step:
            step.log("INFO", "Analyzing macro factors")
            
            # Analyze economic data
            economic_score = self._analyze_economic_data()
            step.log("DEBUG", f"Economic score: {economic_score}")
            
            # Analyze sentiment
            sentiment_score = self._analyze_sentiment()
            step.log("DEBUG", f"Sentiment score: {sentiment_score}")
            
            # Combine scores
            macro_score = (economic_score + sentiment_score) / 2
            
            step.set_output({
                "macro_score": macro_score,
                "economic_score": economic_score,
                "sentiment_score": sentiment_score
            })
            step.set_reasoning(
                f"Macro score {macro_score} based on economic ({economic_score}) "
                f"and sentiment ({sentiment_score}) analysis"
            )
        
        return tracer
```

---

## Best Practices

### 1. Log Meaningful Information
```python
# Good
step.log("INFO", f"Signal score {signal_score} exceeds threshold {threshold}")

# Bad
step.log("INFO", "Signal calculated")
```

### 2. Capture Important Data
```python
# Capture inputs
step.set_input({
    "price": current_price,
    "indicators": {"rsi": rsi, "adx": adx},
    "regime": market_regime
})

# Capture outputs
step.set_output({
    "signal_score": signal_score,
    "direction": "LONG",
    "confidence": 0.85
})
```

### 3. Explain Reasoning
```python
step.set_reasoning(
    f"Signal score {signal_score} exceeds minimum threshold of {threshold}. "
    f"Market regime is {regime} which favors {direction} positions. "
    f"ML model confirms with {ml_confidence}% confidence."
)
```

### 4. Handle Failures Gracefully
```python
with tracer.step("Risk Check", "RiskManager") as step:
    if current_positions >= max_positions:
        step.fail(f"Max positions reached: {current_positions}/{max_positions}")
        tracer.finalize(
            decision_type=DecisionType.TRADE_REJECTED,
            final_decision="No trade",
            confidence=0.0,
            rejection_reason="Maximum position limit reached"
        )
        return None
```

### 5. Skip Optional Steps
```python
with tracer.step("ML Prediction", "ModelInferenceService") as step:
    if not self.model_available:
        step.skip("No ML model deployed")
    else:
        prediction = self.model.predict(features)
        step.set_output(prediction)
```

---

## Debugging with Decision Traces

### Finding Why Trades Were Rejected

1. Go to Decision Trace dashboard
2. Filter by `TRADE_REJECTED`
3. Click on rejected decision
4. Look at `rejection_reason` field
5. Expand failed step to see details
6. Review agent logs for context

### Analyzing Slow Decisions

1. Sort traces by `total_duration_ms`
2. Click on slow decision
3. Review `duration_ms` for each step
4. Identify bottleneck step
5. Review agent logs for that step

### Comparing Successful vs Failed Decisions

1. Filter by symbol (e.g., XAUUSD)
2. Compare TRADE_OPENED vs TRADE_REJECTED
3. Look at differences in:
   - Signal scores
   - Market state
   - Risk checks
   - ML predictions

---

## Performance Considerations

### Memory Management

The tracer stores traces in memory by default. For production:

```python
from core.decision_tracer import clear_old_traces

# Periodically clear old traces (keep last 1000)
clear_old_traces(keep_last_n=1000)
```

### Database Storage (Production)

Modify `DecisionTracer._store_trace()` to save to database:

```python
def _store_trace(self, trace: DecisionTrace):
    # Save to DuckDB
    conn = duckdb.connect('decision_traces.db')
    conn.execute("""
        INSERT INTO decision_traces VALUES (?, ?, ?, ?, ?, ?)
    """, (
        trace.decision_id,
        trace.timestamp,
        trace.symbol,
        trace.decision_type.value,
        json.dumps(asdict(trace)),
        trace.total_duration_ms
    ))
    conn.close()
```

### Selective Tracing

For high-frequency trading, trace only important decisions:

```python
# Only trace if signal is strong or trade is rejected
if signal_score > 8.0 or should_reject:
    tracer = DecisionTracer(symbol=symbol)
    # ... trace decision
else:
    # Skip tracing for weak signals
    pass
```

---

## API Reference

### DecisionTracer

```python
tracer = DecisionTracer(
    symbol: str,
    market_state: Optional[Dict[str, Any]] = None
)
```

**Methods:**
- `step(step_name: str, agent: str)` - Create a step context
- `finalize(decision_type, final_decision, confidence, rejection_reason=None)` - Finalize trace

### StepContext

```python
with tracer.step("Step Name", "Agent") as step:
    # Methods available
```

**Methods:**
- `log(level: str, message: str, context: Optional[Dict] = None)` - Add log entry
- `set_input(data: Dict[str, Any])` - Set input data
- `set_output(data: Dict[str, Any])` - Set output data
- `set_reasoning(reasoning: str)` - Set reasoning
- `fail(reason: Optional[str] = None)` - Mark as failed
- `skip(reason: Optional[str] = None)` - Mark as skipped

### Helper Functions

```python
from core.decision_tracer import get_trace, get_recent_traces, clear_old_traces

# Get specific trace
trace = get_trace(decision_id)

# Get recent traces
traces = get_recent_traces(
    limit=50,
    decision_type=DecisionType.TRADE_REJECTED,
    symbol="XAUUSD"
)

# Clear old traces
clear_old_traces(keep_last_n=1000)
```

---

## Examples

See `examples/decision_tracer_usage.py` for complete examples:

1. **Successful trade decision** - All steps pass
2. **Rejected trade decision** - Failed at signal generation
3. **Integration with FastDecisionEngine** - Real-world usage

Run examples:
```bash
python examples/decision_tracer_usage.py
```

---

## Troubleshooting

### Traces not appearing in dashboard

1. Check backend is running: `http://localhost:8001/api/v1/health`
2. Verify traces are being created: Check logs for "Decision trace finalized"
3. Check API endpoint: `http://localhost:8001/api/v1/decisions/traces`

### Missing agent logs

Ensure you're calling `step.log()` within the step context:
```python
with tracer.step("Step", "Agent") as step:
    step.log("INFO", "Message")  # ✓ Correct
    
log.info("Message")  # ✗ Won't appear in trace
```

### Slow performance

- Reduce trace retention: `clear_old_traces(keep_last_n=500)`
- Use selective tracing for high-frequency decisions
- Implement database storage instead of in-memory

---

## Next Steps

1. **Integrate into your trading logic** - Add tracing to FastDecisionEngine
2. **Review traces in dashboard** - Understand decision patterns
3. **Optimize based on insights** - Identify and fix bottlenecks
4. **Set up alerts** - Monitor for frequent rejections
5. **Analyze performance** - Compare successful vs failed decisions

---

## Support

For issues or questions:
1. Check Decision Trace dashboard for recent decisions
2. Review System Logs for errors
3. Check Bot Control dashboard for system status
4. Consult `examples/decision_tracer_usage.py` for usage patterns

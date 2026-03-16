# Bot Decision History Feature

## Overview
Added a comprehensive "Bot Decision History" section to the Trades tab that shows the reasoning behind each trading decision made by the bot's AI agents.

## Features

### 1. Decision History Table
Shows detailed information about each decision:
- **Timestamp**: When the decision was made
- **Symbol**: Trading pair/asset
- **Decision**: EXECUTED, SKIPPED, or REJECTED
- **Agent**: Which AI agent made the decision (with icon)
- **Signal Score**: Numerical score (0-10) indicating signal strength
- **Key Indicators**: Technical indicators used (RSI, MACD, ADX, etc.)
- **Reasoning**: Detailed explanation of why the decision was made
- **Outcome**: P&L result for executed trades

### 2. Filter Options
Four filter buttons to view specific decision types:
- **ALL**: Show all decisions
- **TRADES**: Only executed trades
- **SKIPPED**: Decisions where bot chose not to trade
- **REJECTED**: Trades rejected by risk management

### 3. Visual Indicators

#### Decision Badges:
- **EXECUTED** (Green): Trade was placed
- **SKIPPED** (Amber): Opportunity identified but not taken
- **REJECTED** (Red): Trade blocked by risk rules
- **PENDING** (Blue): Decision in progress

#### Signal Score Badges:
- **High (7-10)**: Green - Strong signal
- **Medium (5-7)**: Amber - Moderate signal
- **Low (0-5)**: Red - Weak signal

#### Agent Chips:
Color-coded chips showing which agent made the decision:
- 📊 Market Analyst
- 📰 Sentiment Agent
- 📈 Trend Detector
- 🛡️ Risk Manager
- 🔮 Orchestrator

#### Indicator Chips:
Purple chips showing technical indicators used:
- RSI values
- MACD signals
- ADX strength
- Bollinger bands
- Volume analysis
- Support/resistance levels

### 4. Auto-Loading
Decision history automatically loads when:
- User navigates to the Trades tab
- Dashboard is refreshed
- New decisions are made by the bot

## Technical Implementation

### Frontend Components

#### HTML Structure:
```html
<div class="sec-card">
  <div class="sec-header">
    <span class="sec-title">// BOT DECISION HISTORY</span>
    <div class="asset-pills">
      <!-- Filter buttons -->
    </div>
  </div>
  <div class="sec-body">
    <table class="trades-table">
      <!-- Decision rows -->
    </table>
  </div>
</div>
```

#### CSS Classes Added:
- `.decision-badge` - Decision type styling
- `.indicator-chip` - Technical indicator tags
- `.agent-chip` - Agent identification
- `.score-badge` - Signal score display
- `.reasoning-text` - Decision explanation text

### Backend Integration

#### API Endpoint:
```
GET /api/decisions?limit=50
```

#### Expected Response Format:
```json
{
  "decisions": [
    {
      "timestamp": "2026-03-06T10:30:00Z",
      "symbol": "XAUUSD",
      "decision": "EXECUTED",
      "agent": "Market Analyst",
      "agent_icon": "📊",
      "signal_score": 8.5,
      "indicators": ["RSI: 68", "MACD: Bullish", "EMA Cross"],
      "reasoning": "Strong bullish momentum with RSI confirmation",
      "outcome": {
        "pnl": 125.50
      }
    }
  ]
}
```

### JavaScript Functions

#### `loadDecisionHistory()`
- Fetches decision data from API
- Renders table rows with proper styling
- Falls back to mock data if API unavailable
- Updates badge count

#### `filterDecisions(type, el)`
- Filters table rows by decision type
- Updates active filter button
- Shows/hides rows based on selection

#### `generateMockDecisions()`
- Creates realistic demo data
- Used when API endpoint not available
- Helps with frontend development/testing

## Benefits

### For Traders:
1. **Transparency**: See exactly why bot made each decision
2. **Learning**: Understand which indicators work best
3. **Trust**: Build confidence in bot's decision-making
4. **Analysis**: Identify patterns in successful trades
5. **Debugging**: Spot issues with strategy logic

### For Strategy Optimization:
1. **Pattern Recognition**: See which setups lead to wins
2. **Agent Performance**: Compare different agents' success rates
3. **Indicator Effectiveness**: Track which indicators are most reliable
4. **Risk Management**: Review rejected trades to validate rules
5. **Timing Analysis**: Understand when bot skips opportunities

## Usage Examples

### Example 1: Analyzing Successful Trades
1. Navigate to Trades tab
2. Click "TRADES" filter
3. Look for high signal scores (green badges)
4. Note common indicators in winning trades
5. Review reasoning patterns

### Example 2: Understanding Skipped Opportunities
1. Click "SKIPPED" filter
2. Read reasoning for each skip
3. Check if risk rules are too conservative
4. Identify market conditions causing skips

### Example 3: Reviewing Risk Management
1. Click "REJECTED" filter
2. See which trades were blocked
3. Verify risk rules are working correctly
4. Adjust thresholds if needed

## Future Enhancements

### Potential Additions:
1. **Export Functionality**: Download decision history as CSV
2. **Advanced Filters**: Filter by symbol, agent, score range
3. **Statistics Panel**: Win rate by agent, indicator success rates
4. **Decision Replay**: Visualize market conditions at decision time
5. **Comparison View**: Compare similar decisions with different outcomes
6. **Agent Voting**: Show when multiple agents agreed/disagreed
7. **Confidence Intervals**: Display uncertainty in predictions
8. **Time-based Analysis**: Performance by time of day/week
9. **Correlation Analysis**: Link decisions to news events
10. **Decision Trees**: Visualize decision-making flow

## Integration with Backend

To fully enable this feature, the backend needs to:

1. **Log All Decisions**: Store every trading decision in database
2. **Include Metadata**: Save agent, indicators, reasoning, scores
3. **Track Outcomes**: Link decisions to actual trade results
4. **Provide API Endpoint**: Implement `/api/decisions` endpoint
5. **Real-time Updates**: Push new decisions via WebSocket

### Database Schema Suggestion:
```sql
CREATE TABLE bot_decisions (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME,
    symbol VARCHAR(20),
    decision VARCHAR(20),  -- EXECUTED, SKIPPED, REJECTED
    agent VARCHAR(50),
    agent_icon VARCHAR(10),
    signal_score FLOAT,
    indicators JSON,  -- Array of indicator strings
    reasoning TEXT,
    trade_id INTEGER,  -- Link to actual trade if executed
    outcome_pnl FLOAT,  -- Filled when trade closes
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## Testing

The feature includes mock data generation for testing:
- 15 sample decisions with realistic data
- Various decision types and agents
- Different signal scores and outcomes
- Demonstrates all UI components

To test:
1. Open dashboard
2. Navigate to Trades tab
3. View Bot Decision History section
4. Try different filters
5. Inspect decision details

## Notes

- Mock data is used when API endpoint returns error
- Badge shows "(DEMO)" when using mock data
- All styling matches existing dashboard theme
- Responsive design works on different screen sizes
- Tooltips could be added for more details (future enhancement)

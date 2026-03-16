# APEX Architecture Comparison: Old vs New

This document provides a detailed comparison of the old (existing) and new (enhanced) APEX architecture, showing module dependencies and highlighting what changed.

## Legend

- 🟢 **EXISTING** - Original modules that remain unchanged
- 🟡 **ENHANCED** - Original modules with new optional features added
- 🔵 **NEW** - Completely new modules added
- ➡️ **Dependency** - Module A depends on/uses Module B

---

## Old Architecture (Before Enhancement)

### Module Dependency Map - OLD SYSTEM

```
┌─────────────────────────────────────────────────────────────────┐
│                         OLD APEX SYSTEM                          │
│                    (Polling-Based, 15-second)                    │
└─────────────────────────────────────────────────────────────────┘

🟢 MT5 Terminal
    │
    ▼
🟢 core/data_lake.py (MarketDataLake)
    │ - Polls MT5 every 15 seconds
    │ - Caches OHLCV, indicators, news
    │ - Uses DuckDB for storage
    │
    ├──➡️ pandas_ta (for indicators)
    ├──➡️ yfinance (for market data)
    └──➡️ DuckDB (for storage)
    │
    ▼
🟢 core/market_context.py (MarketStateEngine)
    │ - Tracks market regime
    │ - Sector strength analysis
    │ - Correlation tracking
    │
    ▼
🟢 core/fast_decision.py (FastDecisionEngine)
    │ - Rule-based decisions (90% of signals)
    │ - GO/NOGO/NEEDS_REVIEW
    │ - No ML integration
    │
    ▼
🟢 agents/autonomous_orchestrator.py (AutonomousOrchestrator)
    │ - Hybrid decision engine
    │ - Combines fast path + LLM review
    │ - Uses LangGraph for workflow
    │
    ├──➡️ agents/parallel_analyzer.py
    ├──➡️ langchain
    └──➡️ anthropic/openai
    │
    ▼
🟢 core/outcome_tracker.py (OutcomeTracker)
    │ - Tracks decision outcomes
    │ - Adapts thresholds
    │ - Stores in DuckDB
    │
    └──➡️ DuckDB (for outcome storage)

┌─────────────────────────────────────────────────────────────────┐
│                    OLD SYSTEM CHARACTERISTICS                    │
├─────────────────────────────────────────────────────────────────┤
│ ✓ Simple polling architecture (15-second intervals)             │
│ ✓ Rule-based decision making                                    │
│ ✓ No real-time data processing                                  │
│ ✓ No ML model integration                                       │
│ ✓ No systematic training pipeline                               │
│ ✓ No dashboard/visualization                                    │
│ ✓ Limited observability                                         │
└─────────────────────────────────────────────────────────────────┘
```

### Old System Data Flow

```
MT5 Terminal
    │
    │ (Poll every 15s)
    ▼
MarketDataLake
    │
    │ (Cache & compute indicators)
    ▼
MarketStateEngine
    │
    │ (Analyze regime)
    ▼
FastDecisionEngine
    │
    │ (Rule-based logic)
    ▼
AutonomousOrchestrator
    │
    │ (LLM review if needed)
    ▼
OutcomeTracker
    │
    │ (Store results)
    ▼
DuckDB
```

---

## New Architecture (After Enhancement)

### Module Dependency Map - NEW SYSTEM

```
┌─────────────────────────────────────────────────────────────────┐
│                         NEW APEX SYSTEM                          │
│                  (Event-Driven, Real-Time, ML-Enhanced)          │
└─────────────────────────────────────────────────────────────────┘

🔵 MT5 Terminal
    │
    ├──➡️ 🔵 data/collectors/tick_collector.py (TickDataCollector)
    │       │ - Real-time tick capture (<100ms)
    │       │ - Ring buffer (24-hour capacity)
    │       │ - Batch writes to TimescaleDB
    │       └──➡️ TimescaleDB (NEW)
    │
    ├──➡️ 🔵 data/collectors/orderbook_collector.py (OrderBookCollector)
    │       │ - Market depth capture (top 10 levels)
    │       │ - Order imbalance calculation
    │       │ - Large order detection
    │       └──➡️ TimescaleDB (NEW)
    │
    ├──➡️ 🔵 data/collectors/sentiment_analyzer.py (SentimentAnalyzer)
    │       │ - Real-time news sentiment (FinBERT)
    │       │ - Entity extraction
    │       │ - High-impact event detection
    │       └──➡️ DuckDB
    │
    └──➡️ 🔵 data/collectors/alternative_data_collector.py (AltDataCollector)
            │ - On-chain metrics (crypto)
            │ - Social sentiment (Twitter/Reddit)
            │ - Options data (IV, put/call ratio)
            │ - Economic calendar
            └──➡️ DuckDB

    ALL COLLECTORS ──➡️ 🔵 data/event_bus.py (EventBus)
                            │ - asyncio.Queue (max 1000 events)
                            │ - Pub/sub pattern
                            │ - Performance monitoring
                            │
                            ▼
                    🔵 data/feature_pipeline.py (FeaturePipeline)
                            │ - Event-driven processing (<50ms)
                            │ - Incremental indicator updates
                            │ - Feature normalization
                            │
                            ├──➡️ 🔵 data/multi_timeframe_engine.py
                            │       │ - M1, M5, M15, H1, H4, D1
                            │       │ - Trend alignment detection
                            │       │ - Divergence detection
                            │       └──➡️ Redis (feature cache)
                            │
                            ├──➡️ 🔵 data/data_quality_monitor.py
                            │       │ - Missing data detection
                            │       │ - Price spike detection
                            │       │ - Timestamp anomalies
                            │       └──➡️ EventBus (alerts)
                            │
                            └──➡️ 🔵 data/pipeline_metrics.py
                                    │ - Latency tracking
                                    │ - Queue depth monitoring
                                    │ - Throughput metrics
                                    └──➡️ Dashboard

                            ▼
                    Redis (Feature Store) 🔵
                            │ - 1-hour TTL
                            │ - Normalized features
                            │
                            ▼
                    🔵 ml/model_inference_service.py (ModelInferenceService)
                            │ - Low-latency inference (<20ms)
                            │ - Model caching
                            │ - Hot-reloading
                            │
                            ├──➡️ 🔵 ml/model_registry.py (ModelRegistry)
                            │       │ - Version control
                            │       │ - Metadata tracking
                            │       │ - Deployment tagging
                            │       └──➡️ DuckDB (metadata)
                            │
                            ├──➡️ 🔵 ml/supervised_training.py
                            │       │ - XGBoost/LightGBM training
                            │       │ - Walk-forward validation
                            │       │ - Hyperparameter tuning
                            │       └──➡️ ModelRegistry
                            │
                            ├──➡️ 🔵 ml/reinforcement_learning.py
                            │       │ - PPO agent training
                            │       │ - Position sizing optimization
                            │       │ - Sharpe ratio reward
                            │       └──➡️ ModelRegistry
                            │
                            ├──➡️ 🔵 ml/backtesting_engine.py
                            │       │ - Tick-by-tick replay
                            │       │ - Slippage/commission models
                            │       │ - Performance metrics
                            │       └──➡️ ModelRegistry
                            │
                            ├──➡️ 🔵 ml/feature_importance.py
                            │       │ - SHAP value computation
                            │       │ - Feature ranking
                            │       │ - Interaction detection
                            │       └──➡️ Dashboard
                            │
                            ├──➡️ 🔵 ml/ab_testing_framework.py
                            │       │ - Capital allocation
                            │       │ - Statistical testing
                            │       │ - Adaptive rebalancing
                            │       └──➡️ Dashboard
                            │
                            └──➡️ 🔵 ml/model_retraining_pipeline.py
                                    │ - Weekly automated retraining
                                    │ - Model promotion logic
                                    │ - Performance comparison
                                    └──➡️ ModelRegistry

                            ▼
                    🟡 core/fast_decision.py (FastDecisionEngine) [ENHANCED]
                            │ - Rule-based decisions (still works)
                            │ - NOW: Optional ML predictions
                            │ - Backward compatible
                            │
                            ├──➡️ ModelInferenceService (OPTIONAL)
                            └──➡️ 🟢 core/data_lake.py (STILL WORKS)
                            │
                            ▼
                    🟢 agents/autonomous_orchestrator.py (AutonomousOrchestrator)
                            │ - Hybrid decision engine (unchanged)
                            │ - LangGraph workflow (unchanged)
                            │
                            ▼
                    🟢 core/outcome_tracker.py (OutcomeTracker)
                            │ - Tracks outcomes (unchanged)
                            │
                            └──➡️ 🔵 data/trade_journal.py (TradeJournal)
                                    │ - Decision history
                                    │ - Market state capture
                                    │ - Outcome linking
                                    └──➡️ DuckDB

┌─────────────────────────────────────────────────────────────────┐
│                         DASHBOARD LAYER 🔵                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  🔵 api/dashboard_backend.py (FastAPI + WebSocket)              │
│      │ - REST API endpoints                                     │
│      │ - WebSocket real-time updates                            │
│      │ - Rate limiting (100 req/min)                            │
│      │                                                           │
│      ├──➡️ MarketDataLake (market data)                         │
│      ├──➡️ ModelRegistry (model info)                           │
│      ├──➡️ TradeJournal (decisions)                             │
│      ├──➡️ OutcomeTracker (performance)                         │
│      └──➡️ EventBus (real-time events)                          │
│      │                                                           │
│      ▼                                                           │
│  🔵 frontend/dashboard/ (React + Vite)                          │
│      │ - Market State Dashboard                                 │
│      │ - Performance Analytics                                  │
│      │ - Trade Journal                                          │
│      │ - Model Performance                                      │
│      │ - System Health                                          │
│      │                                                           │
│      └──➡️ WebSocket (5-second updates)                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    INTEGRATION LAYER 🔵                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  🔵 data/system_integration.py (SystemIntegration)              │
│      │ - Wires all components together                          │
│      │ - Manages startup/shutdown                               │
│      │ - Graceful error handling                                │
│      │ - Backward compatibility                                 │
│      │                                                           │
│      ├──➡️ EventBus                                             │
│      ├──➡️ FeaturePipeline                                      │
│      ├──➡️ ModelInferenceService                                │
│      ├──➡️ FastDecisionEngine                                   │
│      ├──➡️ MarketDataLake (backward compat)                     │
│      └──➡️ Dashboard WebSocket                                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    NEW SYSTEM CHARACTERISTICS                    │
├─────────────────────────────────────────────────────────────────┤
│ ✓ Event-driven architecture (real-time, <200ms latency)        │
│ ✓ ML-enhanced decision making (optional)                        │
│ ✓ Real-time tick data processing                                │
│ ✓ Systematic ML training pipelines                              │
│ ✓ Model versioning & registry                                   │
│ ✓ Comprehensive dashboard                                       │
│ ✓ Full observability & monitoring                               │
│ ✓ A/B testing framework                                         │
│ ✓ Trade journal & decision tracking                             │
│ ✓ BACKWARD COMPATIBLE with old system                           │
└─────────────────────────────────────────────────────────────────┘
```

### New System Data Flow

```
MT5 Terminal
    │
    │ (Real-time, <100ms)
    ▼
Data Collectors (Tick, OrderBook, Sentiment, AltData)
    │
    │ (Emit events)
    ▼
EventBus (asyncio.Queue)
    │
    │ (Distribute events)
    ▼
FeaturePipeline
    │
    │ (Process events, <50ms)
    ├──➡️ MultiTimeframeEngine
    ├──➡️ DataQualityMonitor
    └──➡️ PipelineMetrics
    │
    │ (Store features)
    ▼
Redis (Feature Store)
    │
    │ (Fetch features)
    ▼
ModelInferenceService
    │
    │ (Predict, <20ms)
    ├──➡️ ModelRegistry
    └──➡️ ML Training Pipelines
    │
    │ (Provide predictions)
    ▼
FastDecisionEngine [ENHANCED]
    │
    │ (Rule-based + ML)
    ├──➡️ MarketDataLake [STILL WORKS]
    └──➡️ ModelInferenceService [OPTIONAL]
    │
    ▼
AutonomousOrchestrator [UNCHANGED]
    │
    │ (LLM review if needed)
    ▼
OutcomeTracker [UNCHANGED]
    │
    │ (Store results)
    ├──➡️ DuckDB
    └──➡️ TradeJournal [NEW]
    │
    ▼
Dashboard [NEW]
    │
    │ (Real-time visualization)
    └──➡️ WebSocket (5-second updates)
```

---

## Side-by-Side Comparison

### Data Collection

| Aspect | OLD 🟢 | NEW 🔵 |
|--------|--------|--------|
| **Method** | Polling (15-second intervals) | Event-driven (real-time) |
| **Latency** | 15+ seconds | <100ms |
| **Data Types** | OHLCV, basic indicators | Tick data, order book, sentiment, alt data |
| **Storage** | DuckDB only | TimescaleDB (tick), DuckDB (historical), Redis (cache) |
| **Module** | `core/data_lake.py` | `data/collectors/*.py` + `core/data_lake.py` (both work) |

### Data Processing

| Aspect | OLD 🟢 | NEW 🔵 |
|--------|--------|--------|
| **Architecture** | Synchronous polling | Asynchronous event-driven |
| **Processing** | Batch (every 15s) | Incremental (per event, <50ms) |
| **Indicators** | Single timeframe | Multi-timeframe (M1-D1) |
| **Quality Checks** | None | Automated (gaps, spikes, anomalies) |
| **Module** | `core/data_lake.py` | `data/feature_pipeline.py` + `data/event_bus.py` |

### ML Integration

| Aspect | OLD 🟢 | NEW 🔵 |
|--------|--------|--------|
| **ML Models** | None | XGBoost, LightGBM, PPO (RL) |
| **Training** | Manual/ad-hoc | Systematic pipelines |
| **Inference** | N/A | <20ms real-time |
| **Versioning** | None | Full model registry |
| **Backtesting** | None | Systematic framework |
| **Module** | N/A | `ml/*.py` (all new) |

### Decision Making

| Aspect | OLD 🟢 | NEW 🟡 |
|--------|--------|--------|
| **Method** | Rule-based only | Rule-based + optional ML |
| **Latency** | ~10ms | ~10ms (rules) + ~20ms (ML if used) |
| **Backward Compat** | N/A | ✅ Works without ML |
| **Module** | `core/fast_decision.py` | `core/fast_decision.py` [ENHANCED] |

### Monitoring & Observability

| Aspect | OLD 🟢 | NEW 🔵 |
|--------|--------|--------|
| **Dashboard** | None | Full React dashboard (5 pages) |
| **Real-time Updates** | None | WebSocket (5-second refresh) |
| **Trade Journal** | None | Complete decision history |
| **Performance Metrics** | Basic | Comprehensive (Sharpe, Sortino, drawdown, etc.) |
| **System Health** | None | Pipeline metrics, data quality, alerts |
| **Module** | N/A | `api/dashboard_backend.py` + `frontend/dashboard/` |

### MLOps

| Aspect | OLD 🟢 | NEW 🔵 |
|--------|--------|--------|
| **Model Registry** | None | Full versioning & metadata |
| **A/B Testing** | None | Statistical framework |
| **Retraining** | Manual | Automated weekly |
| **Feature Importance** | None | SHAP analysis |
| **Model Promotion** | None | Automated based on metrics |
| **Module** | N/A | `ml/model_registry.py`, `ml/ab_testing_framework.py`, etc. |

---

## Module Count Comparison

### OLD System Modules

```
core/
├── data_lake.py              🟢 EXISTING
├── fast_decision.py          🟢 EXISTING
├── market_context.py         🟢 EXISTING
└── outcome_tracker.py        🟢 EXISTING

agents/
├── autonomous_orchestrator.py 🟢 EXISTING
└── parallel_analyzer.py      🟢 EXISTING

Total: 6 core modules
```

### NEW System Modules (Added)

```
data/
├── event_bus.py                          🔵 NEW
├── feature_pipeline.py                   🔵 NEW
├── multi_timeframe_engine.py             🔵 NEW
├── data_quality_monitor.py               🔵 NEW
├── pipeline_metrics.py                   🔵 NEW
├── system_integration.py                 🔵 NEW
├── trade_journal.py                      🔵 NEW
├── historical_data_warehouse.py          🔵 NEW
└── collectors/
    ├── tick_collector.py                 🔵 NEW
    ├── orderbook_collector.py            🔵 NEW
    ├── sentiment_analyzer.py             🔵 NEW
    └── alternative_data_collector.py     🔵 NEW

ml/
├── model_registry.py                     🔵 NEW
├── model_inference_service.py            🔵 NEW
├── supervised_training.py                🔵 NEW
├── reinforcement_learning.py             🔵 NEW
├── backtesting_engine.py                 🔵 NEW
├── feature_importance.py                 🔵 NEW
├── ab_testing_framework.py               🔵 NEW
└── model_retraining_pipeline.py          🔵 NEW

api/
└── dashboard_backend.py                  🔵 NEW

frontend/dashboard/                       🔵 NEW
└── src/
    ├── pages/ (5 dashboard pages)
    ├── components/ (20+ components)
    ├── api/
    └── hooks/

core/
└── fast_decision.py                      🟡 ENHANCED

Total NEW: 28+ modules
Total ENHANCED: 1 module
Total UNCHANGED: 5 modules
```

---

## Key Differences Summary

### 1. **Architecture Pattern**
- **OLD**: Polling-based, synchronous
- **NEW**: Event-driven, asynchronous (with backward compat)

### 2. **Data Processing**
- **OLD**: Batch processing every 15 seconds
- **NEW**: Real-time incremental processing (<200ms end-to-end)

### 3. **ML Integration**
- **OLD**: None
- **NEW**: Full ML pipeline (training, inference, versioning, A/B testing)

### 4. **Observability**
- **OLD**: Minimal logging
- **NEW**: Comprehensive dashboard, metrics, trade journal, alerts

### 5. **Backward Compatibility**
- **OLD**: N/A
- **NEW**: ✅ All old modules still work, new features are optional

### 6. **Deployment**
- **OLD**: Single process
- **NEW**: Modular (can run old system, new system, or hybrid)

---

## Migration Paths

### Path 1: Keep Old System (No Changes)
```python
# Just use existing code
# Nothing breaks
```

### Path 2: Add Dashboard Only
```bash
# Start new dashboard (no code changes)
python -m api.dashboard_backend
npm run dev
```

### Path 3: Add ML Inference
```python
# Enhance FastDecisionEngine with ML
from ml.model_inference_service import ModelInferenceService

model_service = ModelInferenceService(...)
fast_decision = FastDecisionEngine(
    model_inference_service=model_service  # Optional
)
```

### Path 4: Full New System
```python
# Use complete integration
from data.system_integration import SystemIntegration

integration = SystemIntegration(config)
await integration.start()
```

---

## Conclusion

The new system is **additive, not replacement**:

- ✅ All old modules (🟢) continue to work
- ✅ One module (🟡) enhanced with optional features
- ✅ 28+ new modules (🔵) add capabilities
- ✅ System works with any combination of old/new
- ✅ Graceful degradation if new components fail

**You can use the old system, new system, or any hybrid combination.**

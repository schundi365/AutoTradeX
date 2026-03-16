# ML Documentation Index

## Quick Start

New to the ML pipeline? Start here:

1. **[How ML Models Help Trading](./HOW_ML_MODELS_HELP_TRADING.md)** ⭐ START HERE
   - Understand what each model does
   - See real-world examples
   - Learn how models improve profitability

2. **[Quick Reference](./QUICK_REFERENCE.md)**
   - At-a-glance model comparison
   - Common commands
   - Troubleshooting guide

3. **[ML Pipeline Architecture](./ML_PIPELINE_ARCHITECTURE.md)**
   - Visual system overview
   - Data flow diagrams
   - Component interactions

---

## Detailed Documentation

### Core Components

#### Supervised Learning
- **[README.md](./README.md#supervised-learning-training-pipeline)** - Complete supervised learning guide
- **[example_training_usage.py](./example_training_usage.py)** - Training examples
- Models: XGBoost, LightGBM, Random Forest
- Purpose: Predict price direction (UP/DOWN)

#### Reinforcement Learning
- **[README.md](./README.md#reinforcement-learning-pipeline)** - Complete RL guide
- **[example_rl_usage.py](./example_rl_usage.py)** - RL training examples
- Model: PPO Agent
- Purpose: Optimize position sizing

#### Model Management
- **[README.md](./README.md#model-registry-and-versioning)** - Model registry guide
- **[example_model_registry_usage.py](./example_model_registry_usage.py)** - Registry examples
- Features: Versioning, deployment tracking, metadata storage

#### Backtesting
- **[BACKTESTING_README.md](./BACKTESTING_README.md)** - Backtesting guide
- **[example_backtest_usage.py](./example_backtest_usage.py)** - Backtest examples
- Purpose: Validate strategies on historical data

#### A/B Testing
- **[AB_TESTING_README.md](./AB_TESTING_README.md)** - A/B testing guide
- Purpose: Compare model versions safely in production

---

## By Use Case

### I want to...

#### Train a Model
1. Read: [How ML Models Help Trading](./HOW_ML_MODELS_HELP_TRADING.md#supervised-learning-models)
2. Follow: [README.md - Supervised Training](./README.md#basic-training)
3. Run: [example_training_usage.py](./example_training_usage.py)

#### Optimize Position Sizing
1. Read: [How ML Models Help Trading](./HOW_ML_MODELS_HELP_TRADING.md#reinforcement-learning-ppo-agent)
2. Follow: [README.md - RL Training](./README.md#basic-rl-training)
3. Run: [example_rl_usage.py](./example_rl_usage.py)

#### Validate a Strategy
1. Read: [How ML Models Help Trading](./HOW_ML_MODELS_HELP_TRADING.md#backtesting-engine)
2. Follow: [BACKTESTING_README.md](./BACKTESTING_README.md)
3. Run: [example_backtest_usage.py](./example_backtest_usage.py)

#### Deploy a New Model
1. Read: [How ML Models Help Trading](./HOW_ML_MODELS_HELP_TRADING.md#ab-testing-framework)
2. Follow: [AB_TESTING_README.md](./AB_TESTING_README.md)
3. Use: Dashboard → AI & MLOPS tab

#### Understand Model Decisions
1. Read: [How ML Models Help Trading](./HOW_ML_MODELS_HELP_TRADING.md#feature-importance-analysis)
2. Use: `feature_importance.py` module
3. Check: Dashboard → APEX HEALTH tab

#### Monitor Model Performance
1. Read: [Quick Reference](./QUICK_REFERENCE.md#key-metrics-to-monitor)
2. Use: Dashboard → APEX HEALTH tab
3. Check: Model performance metrics daily

---

## File Structure

```
ml/
├── DOCUMENTATION_INDEX.md              ← You are here
├── HOW_ML_MODELS_HELP_TRADING.md      ← Start here for concepts
├── QUICK_REFERENCE.md                  ← Quick lookup
├── ML_PIPELINE_ARCHITECTURE.md         ← System diagrams
├── README.md                           ← Complete technical guide
├── AB_TESTING_README.md                ← A/B testing guide
├── BACKTESTING_README.md               ← Backtesting guide
│
├── supervised_training.py              ← XGBoost/LightGBM training
├── ppo_agent_training.py               ← RL agent training
├── model_inference_service.py          ← Real-time predictions
├── feature_importance.py               ← SHAP analysis
├── ab_testing_framework.py             ← A/B testing
├── model_retraining_pipeline.py        ← Automatic retraining
├── backtesting_engine.py               ← Strategy validation
├── model_registry.py                   ← Model versioning
├── rl_training_environment.py          ← RL environment
├── rl_agent_evaluation.py              ← RL evaluation
│
├── example_training_usage.py           ← Training examples
├── example_rl_usage.py                 ← RL examples
├── example_backtest_usage.py           ← Backtest examples
└── example_model_registry_usage.py     ← Registry examples
```

---

## Learning Path

### Beginner (Day 1-2)
1. Read [How ML Models Help Trading](./HOW_ML_MODELS_HELP_TRADING.md)
2. Review [Quick Reference](./QUICK_REFERENCE.md)
3. Run [example_training_usage.py](./example_training_usage.py)
4. Train your first model from dashboard

### Intermediate (Week 1)
1. Read [ML Pipeline Architecture](./ML_PIPELINE_ARCHITECTURE.md)
2. Study [README.md](./README.md) sections
3. Run backtests on trained models
4. Deploy model to paper trading

### Advanced (Month 1)
1. Train RL agents for position sizing
2. Set up A/B testing for model comparison
3. Configure automatic retraining pipeline
4. Analyze feature importance
5. Deploy to live trading

---

## Common Questions

### Q: Which model should I train first?
**A:** Start with XGBoost for price direction prediction. It's fast to train and provides good baseline performance.

### Q: How long does training take?
**A:** Supervised models: 2-4 hours. RL agents: 8-12 hours. Use the dashboard to monitor progress.

### Q: How do I know if my model is good?
**A:** Check these metrics:
- Accuracy > 52% (better than random)
- Sharpe ratio > 1.5 (good risk-adjusted returns)
- Win rate > 55%
- Max drawdown < 15%

### Q: When should I retrain?
**A:** Retrain weekly automatically, or immediately if:
- Accuracy drops > 5%
- Sharpe ratio < 1.0
- Win rate < 50%

### Q: How do I deploy a model safely?
**A:** Follow this sequence:
1. Backtest on historical data
2. Deploy to paper trading (1-2 weeks)
3. A/B test with 20% traffic
4. Gradually increase to 100%
5. Monitor for 1 week before full rollout

### Q: What if my model performs poorly?
**A:** Check:
1. Training data quality
2. Feature importance (are key features being used?)
3. Hyperparameters (try tuning)
4. Market regime (has market changed?)
5. Consider retraining with more recent data

---

## Support & Resources

### Documentation
- [Main README](./README.md) - Complete technical documentation
- [How ML Models Help](./HOW_ML_MODELS_HELP_TRADING.md) - Conceptual guide
- [Quick Reference](./QUICK_REFERENCE.md) - Quick lookup

### Examples
- [Training Examples](./example_training_usage.py)
- [RL Examples](./example_rl_usage.py)
- [Backtest Examples](./example_backtest_usage.py)
- [Registry Examples](./example_model_registry_usage.py)

### Dashboard
- Training Tab - Train and manage models
- AI & MLOPS Tab - Deploy and monitor models
- APEX Health Tab - Monitor model performance
- Analytics Tab - View trading results

### Code
- `ml/` directory - All ML modules
- `api/ml_endpoints.py` - API endpoints for dashboard
- `tests/` directory - Unit tests

---

## Next Steps

1. **Read** [How ML Models Help Trading](./HOW_ML_MODELS_HELP_TRADING.md) to understand the concepts
2. **Review** [Quick Reference](./QUICK_REFERENCE.md) for commands and metrics
3. **Train** your first model using the dashboard
4. **Backtest** the model to validate performance
5. **Deploy** to paper trading when ready
6. **Monitor** performance and iterate

Good luck with your ML trading journey! 🚀

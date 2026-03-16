# Training History - User Guide

## What Is Training History?

The Training History feature shows you ALL model training attempts in your dashboard, including:
- ✓ **Successful trainings** - Models that met quality standards
- ⚠ **Rejected models** - Models that didn't meet minimum accuracy (52%)
- ✗ **Failed trainings** - Training attempts that crashed or errored

## Where to Find It

Training history appears in TWO places in your dashboard:

1. **MLOps Panel** → "MODEL TRAINING HISTORY" section
2. **Training Tab** → "MODEL TRAINING HISTORY" section

Both show the same data and update automatically.

## Understanding the Display

### Status Colors

| Status | Color | Meaning |
|--------|-------|---------|
| ✓ SUCCESS | Green | Model trained successfully and saved |
| ⚠ REJECTED | Amber | Model trained but accuracy too low (<52%) |
| ✗ FAILED | Red | Training crashed with an error |

### What Each Column Shows

1. **Timestamp** - When you started the training
2. **Status** - Success/Rejected/Failed with model type and symbol
3. **Accuracy** - Model accuracy percentage (if training completed)
4. **Samples** - Number of training/validation samples used
5. **Error** - Why it failed or was rejected (hover for full message)

## Common Scenarios

### Successful Training
```
Timestamp: 3/10/2026, 10:30:45 PM
Status: ✓ SUCCESS (xgboost • XAUUSD)
Accuracy: 58.34%
Samples: 1234/308
Error: (empty)
```
This model trained successfully and is ready to use!

### Rejected Model
```
Timestamp: 3/10/2026, 10:25:12 PM
Status: ⚠ REJECTED (lightgbm • BTCUSD)
Accuracy: 50.12%
Samples: 856/214
Error: Accuracy below minimum threshold (52.0%)
```
The model trained but wasn't good enough. Try:
- Different symbol (XAUUSD or EURUSD work better)
- More training data (increase training_months)
- Different model type

### Failed Training
```
Timestamp: 3/10/2026, 10:20:33 PM
Status: ✗ FAILED (xgboost • XAUUSD)
Accuracy: --
Samples: --
Error: No historical data found for XAUUSD
```
Training couldn't start. You need to import CSV data first!

## How to Use This Information

### 1. Debugging Failed Trainings
Look at the Error column to understand what went wrong:
- "No historical data" → Import CSV files first
- "Insufficient training data" → Need more historical data
- "FeaturePipeline error" → Configuration issue (check logs)

### 2. Improving Model Quality
If you see many REJECTED models:
- Try XAUUSD (Gold) or EURUSD - easier to predict
- Increase training_months from 6 to 12
- Try different model types (XGBoost vs LightGBM)

### 3. Tracking Progress
Watch your success rate improve over time:
- More successful trainings = better data quality
- Higher accuracy = better predictions
- Fewer failures = stable configuration

## Tips for Success

### Best Symbols to Train
1. **XAUUSD (Gold)** - Most predictable, highest success rate
2. **EURUSD** - Stable forex pair, good for learning
3. **GBPUSD** - More volatile but still trainable

### Avoid These Initially
- Crypto (BTCUSD, ETHUSD) - too volatile
- Exotic pairs - insufficient data
- Indices during low volume periods

### Optimal Settings
```
Model Type: XGBoost or LightGBM
Symbol: XAUUSD
Training Months: 6-12
```

## Automatic Updates

Training history refreshes automatically:
- When you load the dashboard
- After training completes (success or failure)
- When you refresh the MLOps panel
- Every time you switch to the Training tab

No manual refresh needed!

## Data Retention

- Keeps last 100 training attempts
- Stored in `data/training_history.json`
- Persists across dashboard restarts
- Can be cleared via API if needed

## Troubleshooting

### History Not Showing?
1. Check if `data/training_history.json` exists
2. Try refreshing the page
3. Check browser console for errors
4. Verify API is running (check dashboard status)

### Old History Showing?
- History updates automatically after each training
- If stuck, refresh the page (F5)
- Check if training actually completed (check logs)

### Want to Start Fresh?
Clear history via API:
```bash
curl -X DELETE http://localhost:8000/api/ml/training-history
```

## Understanding Rejection

### Why Models Get Rejected

Models need at least 52% accuracy to be accepted. This is because:
- 50% = random guessing (coin flip)
- 52% = minimum edge for profitable trading
- Below 52% = worse than random, will lose money

### What to Do When Rejected

1. **Check the data** - Do you have enough historical bars?
2. **Try different symbol** - Some are easier to predict
3. **Increase training period** - More data = better learning
4. **Try different model** - XGBoost vs LightGBM vs PPO
5. **Check logs** - Look for data quality warnings

## Success Metrics

### Good Performance
- Success rate > 60%
- Average accuracy > 55%
- Few failures (< 10%)

### Needs Improvement
- Success rate < 40%
- Many rejections
- Frequent failures

### Action Items
If performance is low:
1. Import more historical data
2. Focus on XAUUSD and EURUSD
3. Increase training_months to 12
4. Check data quality (gaps, errors)

## Next Steps

After reviewing your training history:
1. Identify patterns in successful trainings
2. Replicate successful configurations
3. Avoid symbols/settings that consistently fail
4. Monitor improvement over time

The training history is your guide to building better models!

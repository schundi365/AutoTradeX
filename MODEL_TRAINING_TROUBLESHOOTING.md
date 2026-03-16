# Model Training Troubleshooting

## Error: "Model rejected: accuracy < 52%"

### What This Means

The model trained successfully but didn't perform well enough to be deployed. This is a **safety feature** that prevents bad models from being used in trading.

The acceptance criteria is:
- **Minimum accuracy: 52%** (better than random chance of 50%)

If the model achieves less than 52% accuracy on validation data, it's automatically rejected.

### Why This Happens

1. **Insufficient training data**
   - Not enough historical bars
   - Data quality issues
   - Missing important time periods

2. **Market unpredictability**
   - Some symbols are harder to predict than others
   - Market regime changes
   - High noise-to-signal ratio

3. **Feature quality**
   - Features don't capture important patterns
   - Need more sophisticated indicators

4. **Model configuration**
   - Hyperparameters not optimal for this data
   - Wrong model type for this symbol

### Solutions

#### 1. Try a Different Symbol

Some symbols are easier to predict than others:

**Easier to predict** (try these first):
- XAUUSD (Gold) - Strong trends
- EURUSD - High liquidity, clear patterns
- GBPUSD - Good volatility

**Harder to predict**:
- Crypto pairs - High volatility, noise
- Exotic forex pairs - Low liquidity
- Some indices during ranging markets

#### 2. Increase Training Data

More data = better patterns:

```python
# Default: 6 months
training_months = 6

# Try: 12 months for more data
training_months = 12
```

From dashboard:
- This requires modifying the API endpoint
- Or use the command line script with custom config

#### 3. Try Different Model Types

Each model has strengths:

- **XGBoost**: Best for most cases, handles non-linear patterns
- **LightGBM**: Faster training, good for large datasets
- **Random Forest**: More robust to overfitting

Try all three and see which performs best!

#### 4. Check Your Data Quality

Verify the imported data:

1. Go to **TRAINING** tab
2. Check **DATA WAREHOUSE** section
3. Verify:
   - Enough bars (need 10,000+ for 6 months)
   - Date range covers recent periods
   - No gaps in data

#### 5. Lower the Acceptance Threshold (Not Recommended)

You can modify the minimum accuracy, but this is risky:

In `ml/supervised_training.py`, find `TrainingConfig`:

```python
@dataclass
class TrainingConfig:
    # ...
    min_accuracy: float = 0.52  # Change to 0.50 (but not recommended!)
```

**Warning**: Models with <52% accuracy may lose money in live trading!

### Example: Successful Training

```
Symbol: XAUUSD
Model: XGBoost
Training data: 50,000 bars (6 months)
Result: ✓ Accuracy 58.2% - Model accepted!
```

### Example: Rejected Training

```
Symbol: BTCUSD
Model: XGBoost  
Training data: 15,000 bars (6 months)
Result: ✗ Accuracy 49.8% - Model rejected (< 52%)

Reason: Crypto is too volatile/unpredictable with current features
Solution: Try XAUUSD or EURUSD instead
```

### Checking Actual Accuracy

Look in the logs for the actual accuracy achieved:

```
2024-03-10 22:14:27 | WARNING | Model rejected: accuracy 0.4980 < 0.52
```

This tells you:
- Model achieved 49.8% accuracy
- Needed 52% to pass
- Very close! Try more training data or different symbol

### Best Practices

1. **Start with XAUUSD or EURUSD** - These are most predictable
2. **Use 6-12 months of data** - More is usually better
3. **Try all model types** - XGBoost, LightGBM, Random Forest
4. **Check data quality first** - Ensure you have enough bars
5. **Don't lower acceptance criteria** - 52% is already quite low

### Quick Checklist

Before training:
- [ ] Imported CSV data to warehouse
- [ ] Verified symbol has 10,000+ bars
- [ ] Data covers recent 6+ months
- [ ] Selected appropriate symbol (XAUUSD, EURUSD recommended)
- [ ] Tried multiple model types

If training fails:
- [ ] Check logs for actual accuracy achieved
- [ ] Try different symbol
- [ ] Increase training months
- [ ] Try different model type
- [ ] Verify data quality

### Understanding the Metrics

When a model is accepted, you'll see:

```json
{
  "accuracy": 0.582,    // 58.2% - Good!
  "precision": 0.567,   // 56.7% of BUY predictions were correct
  "recall": 0.598,      // 59.8% of actual UPs were caught
  "f1_score": 0.582,    // Harmonic mean of precision/recall
  "roc_auc": 0.645      // 64.5% - Model can distinguish UP from DOWN
}
```

**Target metrics**:
- Accuracy: >52% (minimum), >55% (good), >58% (excellent)
- ROC AUC: >0.55 (minimum), >0.60 (good), >0.65 (excellent)

### Next Steps After Successful Training

Once a model is accepted:

1. **Review metrics** - Check accuracy, precision, recall
2. **Backtest** - Validate on historical data
3. **Paper trade** - Test with fake money first
4. **Monitor performance** - Track accuracy over time
5. **Retrain weekly** - Keep model updated

### Getting Help

If you're stuck:

1. Check the logs for actual accuracy
2. Verify data quality in warehouse
3. Try the recommended symbols (XAUUSD, EURUSD)
4. Start with XGBoost model type
5. Ensure 6+ months of data

The model rejection is protecting you from deploying a model that would likely lose money. It's better to have no model than a bad model!

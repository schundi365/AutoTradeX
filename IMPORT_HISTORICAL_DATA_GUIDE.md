# Import Historical Data Guide

## Problem

You have historical data in CSV files (`data/raw/*.csv`) but ML training fails with:
```
No historical data found for XAUUSD
```

This is because the ML training pipeline uses the **Historical Data Warehouse** (DuckDB + Parquet), not the raw CSV files directly.

## Solution

Import the CSV files into the warehouse using the import script.

---

## Quick Start

### Step 1: Run the Import Script

```bash
python scripts/import_csv_to_warehouse.py
```

This will:
1. Read all CSV files from `data/raw/`
2. Parse symbol and timeframe from filenames
3. Load and validate the data
4. Store in the Historical Data Warehouse (DuckDB + Parquet)

### Step 2: Verify Import

The script will show:
```
✓ Imported XAUUSD_15m.csv (50000 bars)
✓ Imported XAUUSD_1h.csv (12000 bars)
✓ Imported EURUSD_15m.csv (48000 bars)
...

Import complete: 31 succeeded, 0 failed

Warehouse Statistics:
Total symbols: 16
  XAUUSD_M15: 50,000 bars
  XAUUSD_H1: 12,000 bars
  EURUSD_M15: 48,000 bars
  ...
```

### Step 3: Train Models

Now you can train models from the dashboard:
1. Go to **TRAINING** tab
2. Select model type (XGBoost, LightGBM, etc.)
3. Select symbol (XAUUSD, EURUSD, etc.)
4. Click **START TRAINING**

---

## CSV File Format

Your CSV files should have these columns:
- `timestamp` - Date/time (e.g., "2024-01-01 10:00:00")
- `open` - Opening price
- `high` - High price
- `low` - Low price
- `close` - Closing price
- `volume` - Trading volume

### Filename Format

Files should be named: `{SYMBOL}_{TIMEFRAME}.csv`

Examples:
- `XAUUSD_15m.csv` - Gold, 15-minute bars
- `EURUSD_1h.csv` - EUR/USD, 1-hour bars
- `BTC_USDT_1h.csv` - Bitcoin/USDT, 1-hour bars

### Supported Timeframes

- `15m` → M15 (15 minutes)
- `1h` → H1 (1 hour)
- `4h` → H4 (4 hours)
- `1d` → D1 (1 day)

---

## Your Current Data

You have 31 CSV files in `data/raw/`:

### Forex (Major)
- EURUSD_15m.csv, EURUSD_1h.csv
- GBPUSD_15m.csv, GBPUSD_1h.csv
- USDJPY_15m.csv, USDJPY_1h.csv
- AUDUSD_15m.csv, AUDUSD_1h.csv

### Metals
- XAUUSD_15m.csv, XAUUSD_1h.csv (Gold)
- XAGUSD_15m.csv, XAGUSD_1h.csv (Silver)

### Commodities
- USOIL_15m.csv, USOIL_1h.csv (Oil)

### Crypto
- BTC_15m.csv, BTC_1h.csv, BTC_USDT_1h.csv
- ETH_15m.csv, ETH_1h.csv, ETH_USDT_1h.csv
- BNB_USDT_1h.csv
- SOL_USDT_1h.csv
- XRP_USDT_1h.csv

### Indices
- SP500_15m.csv, SP500_1h.csv
- DXY_15m.csv, DXY_1h.csv (Dollar Index)
- VIX_15m.csv, VIX_1h.csv (Volatility Index)

### Bonds
- US10Y_15m.csv, US10Y_1h.csv (10-Year Treasury)

---

## Troubleshooting

### Import fails with "Invalid filename format"

**Problem**: Filename doesn't match expected format

**Solution**: Rename file to `{SYMBOL}_{TIMEFRAME}.csv`
```bash
# Bad: gold_data.csv
# Good: XAUUSD_15m.csv
```

### Import fails with "Missing columns"

**Problem**: CSV doesn't have required columns

**Solution**: Ensure CSV has: timestamp, open, high, low, close, volume

### Import fails with "Unknown timeframe"

**Problem**: Timeframe not recognized

**Solution**: Use supported timeframes: 15m, 1h, 4h, 1d

### Training still fails after import

**Problem**: Data might not be in the right date range

**Solution**: Check the data range:
```python
from data.historical_data_warehouse import HistoricalDataWarehouse

warehouse = HistoricalDataWarehouse()
stats = warehouse.get_storage_stats()

# Check date ranges
for key, date_range in stats['date_ranges'].items():
    print(f"{key}: {date_range['min']} to {date_range['max']}")
```

---

## Advanced Usage

### Import Specific Files Only

Edit `scripts/import_csv_to_warehouse.py` and modify the main function:

```python
def main():
    warehouse = HistoricalDataWarehouse()
    csv_dir = Path(__file__).parent.parent / "data" / "raw"
    
    # Import only specific files
    files_to_import = [
        "XAUUSD_15m.csv",
        "XAUUSD_1h.csv",
        "EURUSD_15m.csv"
    ]
    
    for filename in files_to_import:
        csv_file = csv_dir / filename
        if csv_file.exists():
            # ... import logic
```

### Re-import (Overwrite Existing Data)

The warehouse will automatically overwrite existing data for the same symbol/timeframe combination.

### Check Warehouse Contents

```python
from data.historical_data_warehouse import HistoricalDataWarehouse

warehouse = HistoricalDataWarehouse()

# Get statistics
stats = warehouse.get_storage_stats()
print(f"Total symbols: {len(stats['row_counts'])}")

# Query specific data
data = warehouse.query_ohlcv(
    symbol="XAUUSD",
    timeframe="M15",
    start=datetime(2024, 1, 1),
    end=datetime(2024, 3, 31)
)
print(f"Retrieved {len(data)} bars")
```

---

## Next Steps

After importing data:

1. **Train Models**
   - Dashboard → TRAINING tab
   - Select XGBoost or LightGBM
   - Choose symbol with imported data
   - Start training

2. **Backtest Strategies**
   - Dashboard → TRAINING tab → Backtesting section
   - Select trained model
   - Run backtest on historical data

3. **Deploy to Paper Trading**
   - Dashboard → AI & MLOPS tab
   - Deploy model to paper trading
   - Monitor performance

---

## Files

- **Import Script**: `scripts/import_csv_to_warehouse.py`
- **CSV Data**: `data/raw/*.csv`
- **Warehouse Storage**: `data/parquet/` (created automatically)
- **Warehouse Database**: `data/historical_data.db` (created automatically)

---

## Summary

1. Run: `python scripts/import_csv_to_warehouse.py`
2. Wait for import to complete
3. Train models from dashboard
4. Profit! 🚀

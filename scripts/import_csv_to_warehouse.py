"""
Import CSV historical data into the Historical Data Warehouse

This script loads CSV files from data/raw/ and imports them into the
DuckDB/Parquet warehouse for ML training.
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.historical_data_warehouse import HistoricalDataWarehouse
from core.logger import get_agent_logger

log = get_agent_logger("CSV_IMPORT")


def parse_csv_filename(filename: str) -> tuple[str, str]:
    """
    Parse CSV filename to extract symbol and timeframe.
    
    Examples:
        XAUUSD_15m.csv -> ("XAUUSD", "M15")
        EURUSD_1h.csv -> ("EURUSD", "H1")
        BTC_USDT_1h.csv -> ("BTC_USDT", "H1")
    """
    name = filename.replace('.csv', '')
    parts = name.rsplit('_', 1)
    
    if len(parts) != 2:
        raise ValueError(f"Invalid filename format: {filename}")
    
    symbol = parts[0]
    timeframe_raw = parts[1]
    
    # Convert timeframe to MT5 format
    timeframe_map = {
        '15m': 'M15',
        '1h': 'H1',
        '4h': 'H4',
        '1d': 'D1',
    }
    
    timeframe = timeframe_map.get(timeframe_raw.lower())
    if not timeframe:
        raise ValueError(f"Unknown timeframe: {timeframe_raw}")
    
    return symbol, timeframe


def load_csv_file(filepath: Path) -> pd.DataFrame:
    """
    Load CSV file and standardize column names.
    
    Expected columns: timestamp, open, high, low, close, volume
    """
    log.info(f"Loading {filepath.name}...")
    
    df = pd.read_csv(filepath)
    
    # Standardize column names (case-insensitive)
    df.columns = df.columns.str.lower()
    
    # Check required columns
    required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    missing_cols = [col for col in required_cols if col not in df.columns]
    
    if missing_cols:
        raise ValueError(f"Missing columns in {filepath.name}: {missing_cols}")
    
    # Convert timestamp to datetime
    if df['timestamp'].dtype == 'object':
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Ensure timezone-naive (remove timezone if present)
    if df['timestamp'].dt.tz is not None:
        df['timestamp'] = df['timestamp'].dt.tz_localize(None)
    
    # Sort by timestamp
    df = df.sort_values('timestamp')
    
    # Remove duplicates
    df = df.drop_duplicates(subset=['timestamp'], keep='last')
    
    log.info(f"Loaded {len(df)} bars from {filepath.name}")
    log.info(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    
    return df[required_cols]


def import_csv_to_warehouse(csv_dir: Path, warehouse: HistoricalDataWarehouse):
    """
    Import all CSV files from directory into warehouse.
    """
    csv_files = list(csv_dir.glob('*.csv'))
    
    if not csv_files:
        log.warning(f"No CSV files found in {csv_dir}")
        return
    
    log.info(f"Found {len(csv_files)} CSV files to import")
    
    imported_count = 0
    failed_count = 0
    
    for csv_file in csv_files:
        try:
            # Parse filename
            symbol, timeframe = parse_csv_filename(csv_file.name)
            
            # Load CSV data
            df = load_csv_file(csv_file)
            
            # Store in warehouse
            log.info(f"Storing {symbol} {timeframe} in warehouse...")
            warehouse.store_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                data=df
            )
            
            log.success(f"✓ Imported {csv_file.name} ({len(df)} bars)")
            imported_count += 1
            
        except Exception as e:
            log.error(f"✗ Failed to import {csv_file.name}: {e}")
            failed_count += 1
    
    log.info(f"\nImport complete: {imported_count} succeeded, {failed_count} failed")
    
    # Show warehouse stats
    stats = warehouse.get_storage_stats()
    log.info("\nWarehouse Statistics:")
    log.info(f"Total symbols: {len(stats['row_counts'])}")
    for key, count in stats['row_counts'].items():
        log.info(f"  {key}: {count:,} bars")


def main():
    """Main import function"""
    log.info("Starting CSV import to Historical Data Warehouse")
    
    # Initialize warehouse
    warehouse = HistoricalDataWarehouse()
    
    # CSV directory
    csv_dir = Path(__file__).parent.parent / "data" / "raw"
    
    if not csv_dir.exists():
        log.error(f"CSV directory not found: {csv_dir}")
        return
    
    # Import all CSV files
    import_csv_to_warehouse(csv_dir, warehouse)
    
    log.success("\n✓ CSV import complete!")
    log.info("You can now train ML models using the imported data")


if __name__ == "__main__":
    main()

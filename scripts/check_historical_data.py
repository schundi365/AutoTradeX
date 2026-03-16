"""
Check Historical Data Coverage

Verifies that collected historical data is sufficient for ML training.
Shows data coverage, gaps, and recommendations.

Usage:
    python scripts/check_historical_data.py
    python scripts/check_historical_data.py --symbol XAUUSD
    python scripts/check_historical_data.py --db data/apex.db
"""
from __future__ import annotations
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import settings
from core.logger import get_agent_logger

log = get_agent_logger("CHECK")


def check_csv_data(data_dir: str = "data/raw", symbol: str = None):
    """Check CSV files in data/raw directory"""
    log.info("=" * 70)
    log.info("CSV Data Coverage Check")
    log.info("=" * 70)
    
    csv_files = list(Path(data_dir).glob("*.csv"))
    
    if not csv_files:
        log.warning(f"No CSV files found in {data_dir}")
        return
    
    if symbol:
        csv_files = [f for f in csv_files if symbol in f.name]
    
    try:
        import pandas as pd
    except ImportError:
        log.error("pandas not installed")
        return
    
    for csv_file in sorted(csv_files):
        try:
            df = pd.read_csv(csv_file)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            symbol_name = csv_file.stem.split('_')[0]
            timeframe = csv_file.stem.split('_')[1] if '_' in csv_file.stem else 'unknown'
            
            bars = len(df)
            start = df['timestamp'].min()
            end = df['timestamp'].max()
            days = (end - start).days
            
            # Calculate if sufficient for training
            min_bars_needed = 10000  # Minimum for good ML training
            status = "✓" if bars >= min_bars_needed else "⚠"
            
            log.info(f"\n{status} {csv_file.name}")
            log.info(f"  Symbol: {symbol_name} | Timeframe: {timeframe}")
            log.info(f"  Bars: {bars:,}")
            log.info(f"  Coverage: {start.date()} to {end.date()} ({days} days / {days/365:.1f} years)")
            
            if bars < min_bars_needed:
                log.warning(f"  ⚠ Insufficient data! Need {min_bars_needed:,} bars for training")
                log.info(f"  Recommendation: Run extended collector for {symbol_name}")
            else:
                log.success(f"  ✓ Sufficient data for ML training")
                
        except Exception as e:
            log.error(f"Error reading {csv_file.name}: {e}")


def check_duckdb_data(db_path: str = None, symbol: str = None):
    """Check data in DuckDB"""
    log.info("\n" + "=" * 70)
    log.info("DuckDB Data Coverage Check")
    log.info("=" * 70)
    
    db_path = db_path or settings.training.duckdb_path
    
    try:
        import duckdb
    except ImportError:
        log.error("duckdb not installed")
        return
    
    try:
        con = duckdb.connect(db_path, read_only=True)
        
        # Check if ohlcv table exists
        tables = con.execute("SHOW TABLES").fetchall()
        if not any('ohlcv' in str(t) for t in tables):
            log.warning("ohlcv table not found in database")
            con.close()
            return
        
        # Get summary by symbol and timeframe
        query = """
            SELECT 
                symbol,
                timeframe,
                COUNT(*) as bars,
                MIN(timestamp) as start_date,
                MAX(timestamp) as end_date,
                DATEDIFF('day', MIN(timestamp), MAX(timestamp)) as days_covered
            FROM ohlcv
        """
        
        if symbol:
            query += f" WHERE symbol = '{symbol}'"
        
        query += " GROUP BY symbol, timeframe ORDER BY symbol, timeframe"
        
        results = con.execute(query).fetchall()
        
        if not results:
            log.warning("No data found in ohlcv table")
            con.close()
            return
        
        min_bars_needed = 10000
        
        for row in results:
            sym, tf, bars, start, end, days = row
            
            status = "✓" if bars >= min_bars_needed else "⚠"
            
            log.info(f"\n{status} {sym} [{tf}]")
            log.info(f"  Bars: {bars:,}")
            log.info(f"  Coverage: {start.date()} to {end.date()} ({days} days / {days/365:.1f} years)")
            
            if bars < min_bars_needed:
                log.warning(f"  ⚠ Insufficient data! Need {min_bars_needed:,} bars for training")
                log.info(f"  Recommendation: python scripts/collect_extended_historical_data.py --symbol {sym} --timeframe {tf}")
            else:
                log.success(f"  ✓ Sufficient data for ML training")
        
        con.close()
        
    except Exception as e:
        log.error(f"Error checking DuckDB: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Check historical data coverage for ML training"
    )
    parser.add_argument(
        "--symbol",
        help="Check specific symbol only"
    )
    parser.add_argument(
        "--db",
        help="DuckDB path (default: from config)"
    )
    parser.add_argument(
        "--csv-dir",
        default="data/raw",
        help="CSV directory (default: data/raw)"
    )
    parser.add_argument(
        "--skip-csv",
        action="store_true",
        help="Skip CSV check"
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Skip DuckDB check"
    )
    
    args = parser.parse_args()
    
    if not args.skip_csv:
        check_csv_data(args.csv_dir, args.symbol)
    
    if not args.skip_db:
        check_duckdb_data(args.db, args.symbol)
    
    log.info("\n" + "=" * 70)
    log.info("Summary")
    log.info("=" * 70)
    log.info("\nMinimum recommended data for ML training:")
    log.info("  • 10,000+ bars per symbol/timeframe")
    log.info("  • 1-2 years of history minimum")
    log.info("  • More data = better model performance")
    log.info("\nTo collect more data:")
    log.info("  python scripts/collect_extended_historical_data.py --symbol XAUUSD --years 2")
    log.info("  python scripts/collect_extended_historical_data.py --all-symbols --years 2")


if __name__ == "__main__":
    main()

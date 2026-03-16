"""
Extended Historical Data Collector for ML Training

Solves the Yahoo Finance intraday limitation by:
1. Fetching daily data for long history (2+ years)
2. Resampling to desired timeframe (15m, 1h, etc.)
3. Fetching recent intraday data to fill gaps
4. Combining both datasets for complete history

This provides sufficient data for ML model training (10,000+ bars).

Usage:
    # Collect 2 years of data resampled to 15m
    python scripts/collect_extended_historical_data.py --years 2 --timeframe 15m
    
    # Collect 3 years for specific symbol
    python scripts/collect_extended_historical_data.py --symbol XAUUSD --years 3
    
    # Use 1h timeframe (more data available)
    python scripts/collect_extended_historical_data.py --timeframe 1h --years 2
"""
from __future__ import annotations
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import settings
from core.logger import get_agent_logger

log = get_agent_logger("HIST")


def collect_extended_data(
    symbol: str,
    years: int = 2,
    target_timeframe: str = "15m",
    output_dir: str = "data/raw"
):
    """
    Collect extended historical data by combining daily and intraday data.
    
    Strategy:
    1. Fetch daily data for full history (2+ years)
    2. Resample to target timeframe
    3. Fetch recent intraday data (last 60 days)
    4. Merge datasets
    
    Args:
        symbol: Symbol name (e.g., 'XAUUSD')
        years: Years of history to collect
        target_timeframe: Target timeframe (15m, 1h, 4h, etc.)
        output_dir: Output directory for CSV files
    """
    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        log.error("yfinance or pandas not installed. Run: pip install yfinance pandas")
        return 0
    
    # Get ticker mapping
    ticker_map = settings.training.yfinance_symbols
    if symbol not in ticker_map:
        log.error(f"Symbol {symbol} not found in yfinance_symbols config")
        return 0
    
    ticker = ticker_map[symbol]
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=years * 365)
    
    log.info(f"Collecting {symbol} ({ticker}) data from {start_date.date()} to {end_date.date()}")
    log.info(f"Target timeframe: {target_timeframe}")
    
    # Step 1: Fetch daily data for full history
    log.info(f"[1/4] Fetching daily data ({years} years)...")
    try:
        daily_df = yf.download(
            ticker,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            interval="1d",
            auto_adjust=True,
            progress=False
        )
        
        if daily_df.empty:
            log.error(f"No daily data returned for {symbol}")
            return 0
        
        # Handle MultiIndex columns
        if isinstance(daily_df.columns, pd.MultiIndex):
            daily_df.columns = [col[0].lower() for col in daily_df.columns]
        else:
            daily_df = daily_df.rename(columns=str.lower)
        
        log.info(f"  ✓ Fetched {len(daily_df):,} daily bars")
    except Exception as e:
        log.error(f"Error fetching daily data: {e}")
        return 0
    
    # Step 2: Resample daily data to target timeframe
    log.info(f"[2/4] Resampling daily data to {target_timeframe}...")
    try:
        # Parse timeframe
        tf_map = {
            "15m": "15T", "30m": "30T", "1h": "1H", "2h": "2H", 
            "4h": "4H", "1d": "1D"
        }
        resample_freq = tf_map.get(target_timeframe, "15T")
        
        # Resample OHLCV data
        resampled = daily_df.resample(resample_freq).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        
        log.info(f"  ✓ Resampled to {len(resampled):,} bars")
    except Exception as e:
        log.error(f"Error resampling data: {e}")
        return 0
    
    # Step 3: Fetch recent intraday data (last 60 days for accuracy)
    log.info(f"[3/4] Fetching recent intraday data (last 60 days)...")
    try:
        intraday_start = end_date - timedelta(days=60)
        
        # Map timeframe to yfinance interval
        yf_interval_map = {
            "15m": "15m", "30m": "30m", "1h": "1h", 
            "2h": "2h", "4h": "4h", "1d": "1d"
        }
        yf_interval = yf_interval_map.get(target_timeframe, "15m")
        
        intraday_df = yf.download(
            ticker,
            start=intraday_start.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            interval=yf_interval,
            auto_adjust=True,
            progress=False
        )
        
        if not intraday_df.empty:
            # Handle MultiIndex columns
            if isinstance(intraday_df.columns, pd.MultiIndex):
                intraday_df.columns = [col[0].lower() for col in intraday_df.columns]
            else:
                intraday_df = intraday_df.rename(columns=str.lower)
            
            log.info(f"  ✓ Fetched {len(intraday_df):,} intraday bars")
        else:
            log.warning("  No intraday data available, using resampled data only")
            intraday_df = None
    except Exception as e:
        log.warning(f"Error fetching intraday data (using resampled only): {e}")
        intraday_df = None
    
    # Step 4: Merge datasets (prefer intraday for recent data)
    log.info(f"[4/4] Merging datasets...")
    try:
        if intraday_df is not None and not intraday_df.empty:
            # Ensure both indexes are timezone-naive datetime64
            if hasattr(resampled.index, 'tz') and resampled.index.tz is not None:
                resampled.index = resampled.index.tz_localize(None)
            if hasattr(intraday_df.index, 'tz') and intraday_df.index.tz is not None:
                intraday_df.index = intraday_df.index.tz_localize(None)
            
            # Remove overlapping period from resampled data
            cutoff = pd.Timestamp(intraday_df.index.min())
            resampled_old = resampled[resampled.index < cutoff]
            
            # Combine
            combined = pd.concat([resampled_old, intraday_df])
            combined = combined.sort_index()
            combined = combined[~combined.index.duplicated(keep='last')]
            
            log.info(f"  ✓ Combined: {len(resampled_old):,} resampled + {len(intraday_df):,} intraday = {len(combined):,} total bars")
        else:
            combined = resampled
            log.info(f"  ✓ Using resampled data only: {len(combined):,} bars")
        
        # Prepare final dataframe
        combined.index.name = "timestamp"
        combined = combined.reset_index()
        combined["symbol"] = symbol
        combined["timeframe"] = target_timeframe
        
        # Reorder columns
        cols = ["timestamp", "symbol", "timeframe", "open", "high", "low", "close", "volume"]
        combined = combined[cols]
        
        # Save to CSV
        output_path = Path(output_dir) / f"{symbol}_{target_timeframe}.csv"
        combined.to_csv(output_path, index=False)
        
        log.success(f"✓ {symbol}: {len(combined):,} bars saved → {output_path}")
        
        # Calculate coverage
        days_covered = (combined['timestamp'].max() - combined['timestamp'].min()).days
        log.info(f"  Coverage: {days_covered} days ({days_covered/365:.1f} years)")
        
        return len(combined)
        
    except Exception as e:
        log.error(f"Error merging datasets: {e}")
        return 0


def load_to_duckdb(csv_path: str, db_path: str = None):
    """Load collected CSV into DuckDB"""
    try:
        import duckdb
        import pandas as pd
    except ImportError:
        log.error("duckdb or pandas not installed")
        return
    
    db_path = db_path or settings.training.duckdb_path
    
    try:
        df = pd.read_csv(csv_path)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        
        con = duckdb.connect(db_path)
        
        # Ensure table exists
        con.execute("""
            CREATE TABLE IF NOT EXISTS ohlcv (
                symbol VARCHAR,
                timeframe VARCHAR,
                timestamp TIMESTAMP,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume DOUBLE,
                PRIMARY KEY (symbol, timeframe, timestamp)
            )
        """)
        
        before = con.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
        
        con.execute("""
            INSERT OR IGNORE INTO ohlcv
            SELECT symbol, timeframe, timestamp, open, high, low, close, volume
            FROM df
        """)
        
        after = con.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
        inserted = after - before
        
        con.close()
        
        log.info(f"✓ Loaded {inserted:,} rows into DuckDB ({db_path})")
        
    except Exception as e:
        log.error(f"Error loading to DuckDB: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Extended historical data collector for ML training"
    )
    parser.add_argument(
        "--symbol",
        default="XAUUSD",
        help="Symbol to collect (default: XAUUSD)"
    )
    parser.add_argument(
        "--years",
        type=int,
        default=2,
        help="Years of history to collect (default: 2)"
    )
    parser.add_argument(
        "--timeframe",
        default="15m",
        choices=["15m", "30m", "1h", "2h", "4h", "1d"],
        help="Target timeframe (default: 15m)"
    )
    parser.add_argument(
        "--output",
        default="data/raw",
        help="Output directory (default: data/raw)"
    )
    parser.add_argument(
        "--db",
        default=None,
        help="DuckDB path (default: from config)"
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Skip loading into DuckDB"
    )
    parser.add_argument(
        "--all-symbols",
        action="store_true",
        help="Collect data for all configured symbols"
    )
    
    args = parser.parse_args()
    
    log.info("=" * 70)
    log.info("APEX Extended Historical Data Collector")
    log.info("=" * 70)
    
    if args.all_symbols:
        symbols = list(settings.training.yfinance_symbols.keys())
        log.info(f"Collecting data for {len(symbols)} symbols: {', '.join(symbols)}")
    else:
        symbols = [args.symbol]
    
    total_bars = 0
    csv_files = []
    
    for symbol in symbols:
        log.info(f"\n{'─' * 70}")
        bars = collect_extended_data(
            symbol=symbol,
            years=args.years,
            target_timeframe=args.timeframe,
            output_dir=args.output
        )
        total_bars += bars
        
        if bars > 0:
            csv_files.append(f"{args.output}/{symbol}_{args.timeframe}.csv")
    
    log.info(f"\n{'=' * 70}")
    log.info(f"Total bars collected: {total_bars:,}")
    log.info(f"Files created: {len(csv_files)}")
    
    # Load to DuckDB
    if not args.skip_db and csv_files:
        log.info(f"\n{'─' * 70}")
        log.info("Loading data into DuckDB...")
        for csv_file in csv_files:
            load_to_duckdb(csv_file, args.db)
    
    log.info(f"\n{'=' * 70}")
    log.success("✓ Collection complete!")
    log.info(f"\nNext steps:")
    log.info(f"  1. Verify data: python scripts/check_historical_data.py")
    log.info(f"  2. Train models: python ml/example_training_usage.py")


if __name__ == "__main__":
    main()

"""
APEX Bot — Historical OHLCV Data Collector
Fetches years of price history from yfinance and Binance (via CCXT).
Saves to CSV in data/raw/ AND loads into DuckDB.

All defaults come from settings.training (configurable via dashboard /api/training/config).

Usage:
    python scripts/collect_historical_data.py
    python scripts/collect_historical_data.py --source yfinance --start 2018-01-01
    python scripts/collect_historical_data.py --source ccxt --symbol BTC/USDT
"""
from __future__ import annotations
import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import settings as _settings


def _effective_start(start: str, interval: str) -> tuple[str, int | None]:
    """Cap start date to yfinance's intraday history window.

    Yahoo limits:
      1m           -> last 7 days
      2m/5m/15m/30m/60m/90m -> last 60 days
      1h           -> last 730 days
      1d / weekly+ -> unlimited

    Returns (effective_start, limit_days).
    limit_days is None when no cap applies (daily/weekly/monthly).
    """
    iv = interval.lower()
    if iv in ("1m",):
        limit = 6
    elif iv.endswith("m") or iv in ("90m",):
        limit = 59
    elif iv in ("1h", "60m"):
        limit = 729
    else:
        return start, None  # daily/weekly/monthly — no cap needed

    earliest = (datetime.utcnow() - timedelta(days=limit)).strftime("%Y-%m-%d")
    # String comparison is safe for ISO dates
    return (earliest, limit) if start < earliest else (start, limit)


def _validate_start(start: str, interval: str) -> str:
    """Validate start date against yfinance's intraday window.

    Prints a clear warning when the requested start is beyond the limit,
    showing what date will actually be used and suggesting alternatives.
    Returns the effective start date to pass to yf.download().
    """
    effective, limit = _effective_start(start, interval)

    if limit is not None and effective != start:
        print(
            f"\n  !! DATE VALIDATION WARNING !!"
            f"\n     Requested start : {start}"
            f"\n     Interval        : {interval}"
            f"\n     Yahoo Finance limit for {interval} data: last {limit} days"
            f"\n     Oldest available : {effective}"
            f"\n     '{start}' is {(datetime.strptime(effective, '%Y-%m-%d') - datetime.strptime(start, '%Y-%m-%d')).days:,} days beyond the limit."
            f"\n     Collection will start from {effective} instead."
            f"\n     TIP: Use interval='1d' in Training Config to fetch daily OHLCV from {start}."
            f"\n"
        )

    return effective

# ─────────────────────────────────────────────────────────────────────────────


def collect_yfinance(
    start: str | None = None,
    end: str | None = None,
    interval: str | None = None,
    out_dir: str | None = None,
    symbols: dict | None = None,
) -> int:
    """Download OHLCV from Yahoo Finance for all configured symbols.

    Defaults come from settings.training so everything is dashboard-configurable.
    """
    t = _settings.training
    start    = start    or t.historical_start_date
    interval = interval or t.yfinance_timeframe
    out_dir  = out_dir  or t.raw_data_dir
    sym_map  = symbols  or t.yfinance_symbols

    try:
        import yfinance as yf
    except ImportError:
        print("ERROR: yfinance not installed. Run: pip install yfinance")
        return 0

    import pandas as pd

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    total_bars = 0

    effective_start = _validate_start(start, interval)

    for name, ticker in sym_map.items():
        try:
            print(f"  Fetching {name} ({ticker}) [{interval}] from {effective_start}...")
            df = yf.download(
                ticker,
                start=effective_start,
                end=end,
                interval=interval,
                auto_adjust=True,
                progress=False,
            )
            if df.empty:
                print(f"    WARNING: No data returned for {name}")
                continue

            # yfinance >= 0.2.x returns MultiIndex columns e.g. ('Close', 'GC=F')
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [col[0].lower() for col in df.columns]
            else:
                df = df.rename(columns=str.lower)
            df.index.name = "timestamp"
            df.reset_index(inplace=True)

            # Standardise columns
            cols = ["timestamp", "open", "high", "low", "close", "volume"]
            available = [c for c in cols if c in df.columns]
            df = df[available]
            df["symbol"] = name
            df["timeframe"] = interval

            out_path = Path(out_dir) / f"{name}_{interval}.csv"
            df.to_csv(out_path, index=False)
            print(f"    {name}: {len(df):,} bars saved → {out_path}")
            total_bars += len(df)
            time.sleep(0.3)  # be polite to Yahoo
        except Exception as e:
            print(f"    ERROR fetching {name}: {e}")

    return total_bars


def collect_ccxt(
    exchange_id: str | None = None,
    timeframe: str | None = None,
    start: str | None = None,
    out_dir: str | None = None,
    symbols: list[str] | None = None,
) -> int:
    """Download full OHLCV history from Binance (or other CCXT exchange).

    Defaults come from settings.training so everything is dashboard-configurable.
    """
    t = _settings.training
    exchange_id = exchange_id or _settings.exchange_id
    timeframe   = timeframe   or t.ccxt_timeframe
    start       = start       or t.ccxt_start_date
    out_dir     = out_dir     or t.raw_data_dir

    try:
        import ccxt
    except ImportError:
        print("ERROR: ccxt not installed. Run: pip install ccxt")
        return 0

    import pandas as pd

    Path(out_dir).mkdir(parents=True, exist_ok=True)

    exchange = getattr(ccxt, exchange_id)()
    since = exchange.parse8601(f"{start}T00:00:00Z")
    targets = symbols or t.ccxt_symbols
    total_bars = 0

    for symbol in targets:
        try:
            print(f"  Fetching {symbol} [{timeframe}] from {start} via {exchange_id}...")
            all_bars = []
            since_ts = since

            while True:
                bars = exchange.fetch_ohlcv(
                    symbol, timeframe, since=since_ts, limit=1000
                )
                if not bars:
                    break
                all_bars.extend(bars)
                since_ts = bars[-1][0] + 1
                time.sleep(exchange.rateLimit / 1000)  # respect rate limit

            if not all_bars:
                print(f"    WARNING: No data for {symbol}")
                continue

            df = pd.DataFrame(
                all_bars,
                columns=["timestamp", "open", "high", "low", "close", "volume"],
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df["symbol"] = symbol.replace("/", "")
            df["timeframe"] = timeframe

            safe_name = symbol.replace("/", "_")
            out_path = Path(out_dir) / f"{safe_name}_{timeframe}.csv"
            df.to_csv(out_path, index=False)
            print(f"    {symbol}: {len(df):,} bars saved → {out_path}")
            total_bars += len(df)
        except Exception as e:
            print(f"    ERROR fetching {symbol}: {e}")

    return total_bars


def load_csv_to_duckdb(csv_dir: str | None = None, db_path: str | None = None):
    """Load all collected CSVs into DuckDB ohlcv table.

    Defaults come from settings.training so everything is dashboard-configurable.
    """
    t = _settings.training
    csv_dir = csv_dir or t.raw_data_dir
    db_path = db_path or t.duckdb_path

    try:
        import duckdb
        import pandas as pd
    except ImportError:
        print("ERROR: duckdb / pandas not installed")
        return

    con = duckdb.connect(db_path)
    csv_files = list(Path(csv_dir).glob("*.csv"))
    if not csv_files:
        print("No CSV files found in", csv_dir)
        return

    total = 0
    for csv_path in csv_files:
        try:
            df = pd.read_csv(csv_path)
            required = {"symbol", "timeframe", "timestamp", "open", "high", "low", "close"}
            if not required.issubset(df.columns):
                print(f"  Skipping {csv_path.name} — missing columns")
                continue
            df["volume"] = df.get("volume", 0.0).fillna(0.0)
            df["timestamp"] = pd.to_datetime(df["timestamp"])

            before = con.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
            con.execute("""
                INSERT OR IGNORE INTO ohlcv
                SELECT symbol, timeframe, timestamp, open, high, low, close, volume
                FROM df
            """)
            after = con.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
            inserted = after - before
            print(f"  {csv_path.name}: +{inserted:,} rows inserted")
            total += inserted
        except Exception as e:
            print(f"  ERROR loading {csv_path.name}: {e}")

    con.close()
    print(f"\nTotal rows inserted into DuckDB: {total:,}")


# ─────────────────────────────────────────────────────────────────────────────

def main():
    t = _settings.training
    parser = argparse.ArgumentParser(
        description="APEX historical data collector (defaults from settings.training)"
    )
    parser.add_argument(
        "--source", choices=["yfinance", "ccxt", "all"], default="all",
        help="Data source to use"
    )
    parser.add_argument("--start",  default=None, help=f"Start date YYYY-MM-DD (default: {t.historical_start_date})")
    parser.add_argument("--end",    default=None, help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--tf",     default=None, help=f"Timeframe (default: {t.yfinance_timeframe})")
    parser.add_argument("--symbol", default=None, help="Single symbol override (CCXT only)")
    parser.add_argument("--out",    default=None, help=f"Output CSV dir (default: {t.raw_data_dir})")
    parser.add_argument("--db",     default=None, help=f"DuckDB path (default: {t.duckdb_path})")
    parser.add_argument("--skip-db", action="store_true", help="Skip loading into DuckDB")
    args = parser.parse_args()

    # Resolve effective values (CLI arg > settings.training default)
    start   = args.start  or t.historical_start_date
    tf      = args.tf     or t.yfinance_timeframe
    out_dir = args.out    or t.raw_data_dir
    db_path = args.db     or t.duckdb_path

    print(f"\n{'='*60}")
    print("APEX Historical Data Collector")
    print(f"  Start  : {start}  |  Timeframe: {tf}")
    print(f"  Out    : {out_dir}  |  DB: {db_path}")
    print(f"{'='*60}\n")

    total = 0

    if args.source in ("yfinance", "all"):
        print("[yfinance] Fetching forex, metals, indices...")
        total += collect_yfinance(
            start=start, end=args.end, interval=tf, out_dir=out_dir
        )

    if args.source in ("ccxt", "all"):
        print("\n[CCXT/Binance] Fetching crypto OHLCV...")
        syms = [args.symbol] if args.symbol else None
        total += collect_ccxt(
            timeframe=tf, start=start, out_dir=out_dir, symbols=syms
        )

    print(f"\nTotal bars collected: {total:,}")

    if not args.skip_db and total > 0:
        print("\nLoading CSVs into DuckDB...")
        load_csv_to_duckdb(csv_dir=out_dir, db_path=db_path)

    print("\nDone.")


if __name__ == "__main__":
    main()

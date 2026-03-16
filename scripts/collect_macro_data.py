"""
APEX Bot — Macro Data Collector
Downloads macro indicators for training the Macro Agent.

Sources:
  1. FRED API (free key at fred.stlouisfed.org)
     - DXY (broad USD index), US10Y, VIX, CPI, Fed Funds Rate, Gold price
  2. CFTC COT Reports (Commitment of Traders)
     - Commercial vs. speculative positioning on Gold futures
     - Published every Friday — no API key needed

Usage:
    python scripts/collect_macro_data.py
    python scripts/collect_macro_data.py --fred-key YOUR_KEY
    python scripts/collect_macro_data.py --source cot
"""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import settings as _settings

# Resolved lazily from settings so the dashboard can override before scripts run


def collect_fred(
    api_key: str | None = None,
    start: str | None = None,
    series: dict | None = None,
    out_dir: str | None = None,
) -> int:
    """Download macro time series from FRED.

    All defaults come from settings.training so they are dashboard-configurable.
    """
    t = _settings.training
    api_key  = api_key  or t.fred_api_key
    start    = start    or t.historical_start_date
    fred_map = series   or t.fred_series
    out_path = Path(out_dir or t.macro_data_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    try:
        from fredapi import Fred
        import pandas as pd
    except ImportError:
        print("ERROR: fredapi not installed. Run: pip install fredapi pandas")
        return 0

    if not api_key:
        print("ERROR: FRED API key required. Get free key at https://fred.stlouisfed.org/docs/api/api_key.html")
        print("  Set it in dashboard under Training > Configuration, or as FRED_API_KEY env var")
        return 0

    fred = Fred(api_key=api_key)
    all_series = {}
    fetched = 0

    print(f"  [FRED] Fetching {len(fred_map)} macro series from {start}...")
    for series_id, name in fred_map.items():
        try:
            s = fred.get_series(series_id, observation_start=start)
            s.name = name
            all_series[name] = s
            print(f"    {name}: {len(s):,} observations")
            fetched += len(s)
        except Exception as e:
            print(f"    WARNING: {name} ({series_id}) failed: {e}")

    if not all_series:
        return 0

    # Merge into single DataFrame
    df = pd.DataFrame(all_series)
    df.index.name = "date"
    df.reset_index(inplace=True)

    # Compute daily changes (key features for Macro Agent)
    if "DXY" in df.columns:
        df["DXY_change_pct"] = df["DXY"].pct_change() * 100
    if "US10Y" in df.columns:
        df["US10Y_change_bps"] = df["US10Y"].diff() * 100  # bps
    if "GOLD" in df.columns:
        df["GOLD_change_pct"] = df["GOLD"].pct_change() * 100

    # Add macro regime classification
    def classify_regime(row):
        dxy_chg = row.get("DXY_change_pct", 0.0)
        us10y_chg = row.get("US10Y_change_bps", 0.0)
        if dxy_chg > 0.8:
            return "SEVERE_RISK_OFF"
        elif dxy_chg > 0.3 or us10y_chg > 5:
            return "RISK_OFF"
        elif dxy_chg < -0.2 and us10y_chg < -3:
            return "RISK_ON"
        return "NEUTRAL"

    df["macro_regime"] = df.apply(classify_regime, axis=1)

    out = out_path / "fred_macro_daily.csv"
    df.to_csv(out, index=False)
    print(f"\n  Combined macro DataFrame: {len(df):,} rows → {out}")
    return fetched


# ─────────────────────────────────────────────────────────────────────────────
# 2. CFTC COT Reports — Commitment of Traders (Gold futures)
# ─────────────────────────────────────────────────────────────────────────────

def collect_cot(out_dir: str | None = None) -> int:
    """Download CFTC COT report and extract Gold futures positioning.

    out_dir defaults to settings.training.macro_data_dir.
    """
    out_path = Path(out_dir or _settings.training.macro_data_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    try:
        import pandas as pd
        import requests
    except ImportError:
        print("ERROR: pandas/requests not installed")
        return 0

    print("  [CFTC COT] Downloading Commitment of Traders report...")

    # CFTC moved from a single deacot.zip to per-year archives in 2024.
    # Download current year + previous year to get ~2 years of weekly data.
    try:
        import io
        import zipfile
        from datetime import datetime as _dt

        current_year = _dt.utcnow().year
        years_to_fetch = [current_year, current_year - 1]
        frames = []

        for year in years_to_fetch:
            url = f"https://www.cftc.gov/files/dea/history/deacot{year}.zip"
            print(f"    Fetching {url} ...")
            r = requests.get(url, timeout=120)
            if r.status_code != 200:
                print(f"    WARNING: CFTC returned {r.status_code} for {year} — skipping")
                continue
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                csv_name = z.namelist()[0]
                with z.open(csv_name) as f:
                    frames.append(pd.read_csv(f, low_memory=False))
            print(f"    {year}: {len(frames[-1]):,} rows downloaded")

        if not frames:
            print("    ERROR: No COT data could be downloaded")
            return 0

        df = pd.concat(frames, ignore_index=True).drop_duplicates()
        print(f"    Combined COT: {len(df):,} rows across all markets")

        # CFTC 2024+ format uses spaces instead of underscores in column names.
        # Normalise all column names to lowercase with underscores for consistency.
        df.columns = (
            df.columns.str.strip()
                      .str.lower()
                      .str.replace(r"[\s\-/()%]+", "_", regex=True)
                      .str.strip("_")
        )

        # Market name column (normalised)
        mkt_col = next((c for c in df.columns if "market" in c and "exchange" in c), None)
        if mkt_col is None:
            print("    ERROR: Cannot find market name column in COT data")
            return 0

        # Filter for Gold futures
        gold_cot = df[df[mkt_col].astype(str).str.contains("GOLD", case=False, na=False)].copy()

        if gold_cot.empty:
            print("    WARNING: No Gold rows found in COT data")
            return 0

        # Resolve date column — prefer YYYY-MM-DD, fall back to YYMMDD
        date_col_iso = next((c for c in gold_cot.columns if "yyyy" in c), None)
        date_col_yy  = next((c for c in gold_cot.columns if "yymmdd" in c and "yyyy" not in c), None)
        if date_col_iso:
            gold_cot["date"] = pd.to_datetime(gold_cot[date_col_iso], errors="coerce")
        elif date_col_yy:
            gold_cot["date"] = pd.to_datetime(gold_cot[date_col_yy], format="%y%m%d", errors="coerce")
        else:
            gold_cot["date"] = pd.NaT

        # Resolve position columns by partial name match
        def _find_col(df, *keywords):
            for c in df.columns:
                if all(k in c for k in keywords):
                    return c
            return None

        comm_long  = _find_col(gold_cot, "commercial", "long",  "all")
        comm_short = _find_col(gold_cot, "commercial", "short", "all")
        spec_long  = _find_col(gold_cot, "noncommercial", "long",  "all")
        spec_short = _find_col(gold_cot, "noncommercial", "short", "all")

        if comm_long and comm_short:
            gold_cot["commercial_net"] = gold_cot[comm_long] - gold_cot[comm_short]
        if spec_long and spec_short:
            gold_cot["speculative_net"] = gold_cot[spec_long] - gold_cot[spec_short]

        def cot_signal(row):
            comm_net = row.get("commercial_net", 0) or 0
            spec_net = row.get("speculative_net", 0) or 0
            if comm_net < -100000:
                return "BEARISH"
            elif comm_net > 50000:
                return "BULLISH"
            elif spec_net > 200000:
                return "CONTRARIAN_BEARISH"
            return "NEUTRAL"

        gold_cot["cot_signal"] = gold_cot.apply(cot_signal, axis=1)

        # Keep only the columns we need
        out_cols = ["date", "commercial_net", "speculative_net", "cot_signal"]
        gold_cot = gold_cot[[c for c in out_cols if c in gold_cot.columns]].dropna(subset=["date"])
        gold_cot = gold_cot.sort_values("date").drop_duplicates("date")

        out = out_path / "cot_gold.csv"
        gold_cot.to_csv(out, index=False)
        print(f"    Gold COT: {len(gold_cot)} weekly reports saved to {out}")
        return len(gold_cot)

    except Exception as e:
        print(f"    ERROR fetching COT data: {e}")
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# 3. Load macro data into DuckDB
# ─────────────────────────────────────────────────────────────────────────────

def load_macro_to_duckdb(db_path: str | None = None, macro_dir: str | None = None):
    """Create a macro_daily table and load FRED data into DuckDB.

    Both default to settings.training values so they are dashboard-configurable.
    """
    t = _settings.training
    db_path  = db_path   or t.duckdb_path
    macro_dir = macro_dir or t.macro_data_dir

    try:
        import duckdb
        import pandas as pd
    except ImportError:
        print("ERROR: duckdb/pandas not installed")
        return

    fred_csv = Path(macro_dir) / "fred_macro_daily.csv"
    if not fred_csv.exists():
        print("  No FRED CSV found — skipping DuckDB load")
        return

    con = duckdb.connect(db_path)
    try:
        df = pd.read_csv(fred_csv)
        df["date"] = pd.to_datetime(df.get("date", df.index))

        # Normalise column names: capitalised FRED names → lowercase snake_case
        col_map = {
            "DXY":            "dxy",
            "US10Y":          "us10y",
            "VIX":            "vix",
            "GOLD":           "gold",
            "CPI":            "cpi",
            "FED_RATE":       "fed_rate",
            "EURUSD":         "eurusd",
            "GBPUSD":         "gbpusd",
            "BREAKEVEN_10Y":  "breakeven_10y",
            "US2Y":           "us2y",
            "DXY_change_pct":   "dxy_change_pct",
            "US10Y_change_bps": "us10y_change_bps",
            "GOLD_change_pct":  "gold_change_pct",
            "macro_regime":     "macro_regime",
        }
        df = df.rename(columns={src: dst for src, dst in col_map.items() if src in df.columns})
        df.columns = df.columns.str.lower()  # catch any remaining uppercase columns

        # Deduplicate on date before inserting
        df = df.drop_duplicates(subset=["date"]).sort_values("date")

        # CREATE OR REPLACE TABLE infers schema from the DataFrame — handles
        # any number of columns without hardcoding, and survives schema changes
        # between runs when new FRED series are added/removed.
        con.execute("CREATE OR REPLACE TABLE macro_daily AS SELECT * FROM df")
        count = con.execute("SELECT COUNT(*) FROM macro_daily").fetchone()[0]
        cols  = con.execute("DESCRIBE macro_daily").df()["column_name"].tolist()
        print(f"  macro_daily table: {count:,} rows, {len(cols)} columns in DuckDB")
        print(f"    columns: {', '.join(cols)}")
    except Exception as e:
        print(f"  ERROR loading macro to DuckDB: {e}")
    finally:
        con.close()


# ─────────────────────────────────────────────────────────────────────────────

def main():
    t = _settings.training
    parser = argparse.ArgumentParser(
        description="APEX macro data collector (defaults from settings.training)"
    )
    parser.add_argument(
        "--source", choices=["fred", "cot", "all"], default="all",
        help="Data source"
    )
    parser.add_argument(
        "--fred-key", default=None,
        help=f"FRED API key (default: FRED_API_KEY env / training config). "
             f"Free at fred.stlouisfed.org"
    )
    parser.add_argument("--start",   default=None, help=f"Start date (default: {t.historical_start_date})")
    parser.add_argument("--db",      default=None, help=f"DuckDB path (default: {t.duckdb_path})")
    parser.add_argument("--out",     default=None, help=f"Output dir (default: {t.macro_data_dir})")
    parser.add_argument("--skip-db", action="store_true", help="Skip DuckDB load")
    args = parser.parse_args()

    # Resolve effective values
    fred_key  = args.fred_key or t.fred_api_key
    start     = args.start    or t.historical_start_date
    db_path   = args.db       or t.duckdb_path
    macro_dir = args.out      or t.macro_data_dir

    print(f"\n{'='*60}")
    print("APEX Macro Data Collector")
    print(f"  FRED key : {'set' if fred_key else 'NOT SET'}")
    print(f"  Start    : {start}  |  DB: {db_path}")
    print(f"  Out dir  : {macro_dir}")
    print(f"{'='*60}\n")

    total = 0

    if args.source in ("fred", "all"):
        print("[FRED API] Macro indicators...")
        if not fred_key:
            print("  TIP: Set FRED_API_KEY env var or configure via dashboard /api/training/config")
            print("       Free key at https://fred.stlouisfed.org/docs/api/api_key.html")
            print("  Skipping FRED (no key provided)\n")
        else:
            total += collect_fred(api_key=fred_key, start=start, out_dir=macro_dir)

    if args.source in ("cot", "all"):
        print("\n[CFTC COT] Gold futures positioning...")
        total += collect_cot(out_dir=macro_dir)

    print(f"\nTotal macro records collected: {total:,}")

    if not args.skip_db:
        print("\nLoading into DuckDB...")
        load_macro_to_duckdb(db_path=db_path, macro_dir=macro_dir)

    print("\nDone.")
    print("\nNext steps:")
    print("  1. Run collect_historical_data.py for OHLCV price data")
    print("  2. Run collect_sentiment_data.py for news/sentiment data")
    print("  3. Start paper trading — log decisions via log_decision_context()")
    print("  4. After 200+ decisions: run prepare_training_data.py")


if __name__ == "__main__":
    main()

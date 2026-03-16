#!/usr/bin/env python3
"""Check decision data."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from memory.duckdb_store import DuckDBStore
from core.config import settings

store = DuckDBStore(settings.training.duckdb_path)

# Check decision_log
try:
    count = store.execute_read("SELECT COUNT(*) FROM decision_log")
    print(f"decision_log: {count[0][0]} rows")
    
    if count[0][0] > 0:
        sample = store.execute_read("SELECT timestamp, symbol, outcome FROM decision_log ORDER BY timestamp DESC LIMIT 5")
        print("\nRecent decisions:")
        for row in sample:
            print(f"  {row[0]} | {row[1]} | {row[2]}")
except Exception as e:
    print(f"decision_log error: {e}")

# Check bot_decisions
try:
    count = store.execute_read("SELECT COUNT(*) FROM bot_decisions")
    print(f"\nbot_decisions: {count[0][0]} rows")
    
    if count[0][0] > 0:
        sample = store.execute_read("SELECT timestamp, symbol, decision FROM bot_decisions ORDER BY timestamp DESC LIMIT 5")
        print("\nRecent bot decisions:")
        for row in sample:
            print(f"  {row[0]} | {row[1]} | {row[2]}")
except Exception as e:
    print(f"bot_decisions error: {e}")

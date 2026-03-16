#!/usr/bin/env python3
"""Test apex health query directly."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from memory.duckdb_store import DuckDBStore
from core.config import settings
from datetime import datetime, timedelta

store = DuckDBStore(settings.training.duckdb_path)

day_ago = datetime.utcnow() - timedelta(days=1)
print(f"Querying for data after: {day_ago}")

llm_calls = store.execute_read("""
    SELECT 
        COUNT(*) as total_calls,
        AVG(latency_ms) as avg_latency,
        SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
        SUM(CASE WHEN timeout = 1 THEN 1 ELSE 0 END) as timeouts,
        SUM(CASE WHEN error = 1 THEN 1 ELSE 0 END) as errors
    FROM llm_calls
    WHERE timestamp >= ? AND tier = 'ollama'
""", [day_ago])

print(f"\nQuery result: {llm_calls}")

if llm_calls and llm_calls[0][0] > 0:
    total_calls, avg_latency, successes, timeouts, errors = llm_calls[0]
    print(f"\nTotal calls: {total_calls}")
    print(f"Avg latency: {avg_latency}")
    print(f"Successes: {successes}")
    print(f"Timeouts: {timeouts}")
    print(f"Errors: {errors}")
else:
    print("\nNo data found!")

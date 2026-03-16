#!/usr/bin/env python3
"""Check LLM calls data."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from memory.duckdb_store import DuckDBStore
from core.config import settings
from datetime import datetime, timedelta

store = DuckDBStore(settings.training.duckdb_path)

# Check all LLM calls
rows = store.execute_read("SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM llm_calls")
print(f"Total LLM calls: {rows[0][0]}")
print(f"Min timestamp: {rows[0][1]}")
print(f"Max timestamp: {rows[0][2]}")

# Check by tier
rows = store.execute_read("SELECT tier, COUNT(*) FROM llm_calls GROUP BY tier")
print("\nBy tier:")
for row in rows:
    print(f"  {row[0]}: {row[1]}")

# Check last 24 hours
day_ago = datetime.utcnow() - timedelta(days=1)
print(f"\nDay ago: {day_ago}")

rows = store.execute_read("SELECT COUNT(*) FROM llm_calls WHERE timestamp >= ?", [day_ago])
print(f"Calls in last 24h: {rows[0][0]}")

rows = store.execute_read("SELECT COUNT(*) FROM llm_calls WHERE tier = 'ollama' AND timestamp >= ?", [day_ago])
print(f"Ollama calls in last 24h: {rows[0][0]}")

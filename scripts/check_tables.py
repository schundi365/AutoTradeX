#!/usr/bin/env python3
"""Check database tables and data."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from memory.duckdb_store import DuckDBStore
from core.config import settings
import asyncio

async def check():
    store = DuckDBStore(settings.training.duckdb_path)
    await store.start()
    
    # Check tables
    tables = store.execute_read("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'")
    print("Tables:", [t[0] for t in tables])
    
    # Check bot_decisions
    try:
        count = store.execute_read("SELECT COUNT(*) FROM bot_decisions")
        print(f"\nbot_decisions: {count[0][0]} rows")
        
        sample = store.execute_read("SELECT * FROM bot_decisions LIMIT 3")
        print("Sample rows:", sample)
    except Exception as e:
        print(f"bot_decisions error: {e}")
    
    # Check llm_calls
    try:
        count = store.execute_read("SELECT COUNT(*) FROM llm_calls")
        print(f"\nllm_calls: {count[0][0]} rows")
        
        sample = store.execute_read("SELECT * FROM llm_calls LIMIT 3")
        print("Sample rows:", sample)
    except Exception as e:
        print(f"llm_calls error: {e}")
    
    await store.stop()

if __name__ == "__main__":
    asyncio.run(check())

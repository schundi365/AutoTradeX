#!/usr/bin/env python3
"""Quick script to check bot_decisions table"""
import asyncio
from memory.duckdb_store import DuckDBStore
from core.config import settings

async def main():
    store = DuckDBStore(settings.training.duckdb_path)
    await store.start()
    
    try:
        # Check bot_decisions table
        rows = store.execute_read('SELECT COUNT(*) FROM bot_decisions', [])
        count = rows[0][0] if rows else 0
        print(f"bot_decisions table has {count} rows")
        
        if count > 0:
            # Show sample
            sample = store.execute_read('''
                SELECT timestamp, symbol, decision, confidence, decision_time_ms 
                FROM bot_decisions 
                ORDER BY timestamp DESC 
                LIMIT 5
            ''', [])
            print("\nSample decisions:")
            for row in sample:
                print(f"  {row[0]} | {row[1]} | {row[2]} | conf={row[3]:.2f} | time={row[4]}ms")
    except Exception as e:
        print(f"Error checking bot_decisions: {e}")
        
        # Try decision_log as fallback
        try:
            rows = store.execute_read('SELECT COUNT(*) FROM decision_log', [])
            count = rows[0][0] if rows else 0
            print(f"\nFallback: decision_log table has {count} rows")
        except Exception as e2:
            print(f"Error checking decision_log: {e2}")
    
    await store.stop()

if __name__ == "__main__":
    asyncio.run(main())

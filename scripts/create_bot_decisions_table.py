"""
Create bot_decisions table via API call.
This script creates the table without needing to stop the bot.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from memory.duckdb_store import DuckDBStore
from core.config import settings
from loguru import logger as log


async def create_table():
    """Create bot_decisions table."""
    store = DuckDBStore(settings.training.duckdb_path)
    
    try:
        await store.start()
        
        log.info("Creating bot_decisions table...")
        await store.execute_write("""
            CREATE TABLE IF NOT EXISTS bot_decisions (
                id INTEGER PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                symbol VARCHAR,
                decision VARCHAR,
                confidence DOUBLE,
                outcome VARCHAR,
                decision_time_ms INTEGER
            )
        """)
        
        log.info("Creating index on bot_decisions...")
        await store.execute_write("""
            CREATE INDEX IF NOT EXISTS idx_bot_decisions_time ON bot_decisions (timestamp)
        """)
        
        log.success("✓ bot_decisions table created successfully!")
        
        # Verify table exists
        result = await store.execute_read("""
            SELECT COUNT(*) as count FROM bot_decisions
        """)
        log.info(f"Table verified: {result[0][0]} rows")
        
    except Exception as e:
        log.error(f"Failed to create table: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await store.stop()


if __name__ == "__main__":
    asyncio.run(create_table())

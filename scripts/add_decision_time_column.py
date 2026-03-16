#!/usr/bin/env python3
"""
Add decision_time_ms column to existing bot_decisions table without losing data.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from memory.duckdb_store import DuckDBStore
from core.config import settings
from core.logger import setup_logging, get_agent_logger

setup_logging()
log = get_agent_logger("MIGRATE")

async def add_column():
    """Add decision_time_ms column to bot_decisions table."""
    store = DuckDBStore(settings.training.duckdb_path)
    await store.start()
    
    try:
        # Check if column already exists
        columns = store.execute_read("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'bot_decisions'
        """)
        
        column_names = [col[0] for col in columns]
        log.info("Current columns in bot_decisions: {}", column_names)
        
        if 'decision_time_ms' in column_names:
            log.info("✓ Column decision_time_ms already exists")
            await store.stop()
            return
        
        # Add the column
        log.info("Adding decision_time_ms column...")
        await store.execute_write("""
            ALTER TABLE bot_decisions 
            ADD COLUMN decision_time_ms INTEGER
        """)
        
        log.info("✓ Column decision_time_ms added successfully")
        
        # Verify
        columns = store.execute_read("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'bot_decisions'
        """)
        
        column_names = [col[0] for col in columns]
        log.info("Updated columns: {}", column_names)
        
        # Check row count to confirm no data loss
        count = store.execute_read("SELECT COUNT(*) FROM bot_decisions")
        log.info("✓ Row count: {} (no data lost)", count[0][0])
        
        await store.stop()
        
        log.info("")
        log.info("✅ Migration complete!")
        log.info("You can now restart the bot.")
        
    except Exception as e:
        log.error("Migration failed: {}", e)
        import traceback
        traceback.print_exc()
        await store.stop()
        raise

if __name__ == "__main__":
    import asyncio
    asyncio.run(add_column())

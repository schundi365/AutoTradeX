#!/usr/bin/env python3
"""
Initialize DuckDB tables for Apex Trader health monitoring.
Run this once to create the required tables.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from memory.duckdb_store import DuckDBStore
from core.config import settings
from core.logger import setup_logging, get_agent_logger

setup_logging()
log = get_agent_logger("INIT")

async def init_tables():
    """Create tables for Apex health monitoring."""
    store = DuckDBStore(settings.training.duckdb_path)
    await store.start()
    
    try:
        # Table 1: LLM call logs
        log.info("Creating llm_calls table...")
        await store.execute_write("""
            CREATE TABLE IF NOT EXISTS llm_calls (
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                agent VARCHAR,
                tier VARCHAR,
                model VARCHAR,
                latency_ms INTEGER,
                success INTEGER,
                timeout INTEGER,
                error INTEGER
            )
        """)
        
        log.info("✓ llm_calls table created")
        
        # Table 2: Bot decision outcomes
        log.info("Creating bot_decisions table...")
        await store.execute_write("""
            CREATE TABLE IF NOT EXISTS bot_decisions (
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                symbol VARCHAR,
                decision VARCHAR,
                confidence FLOAT,
                outcome VARCHAR,
                decision_time_ms INTEGER
            )
        """)
        
        log.info("✓ bot_decisions table created")
        
        # Table 3: Model metadata
        log.info("Creating model_metadata table...")
        await store.execute_write("""
            CREATE TABLE IF NOT EXISTS model_metadata (
                model_type VARCHAR,
                model_name VARCHAR,
                last_trained TIMESTAMP,
                training_samples INTEGER,
                accuracy FLOAT,
                notes VARCHAR
            )
        """)
        
        log.info("✓ model_metadata table created")
        
        # Insert initial model metadata
        log.info("Inserting initial model metadata...")
        await store.execute_write("""
            INSERT INTO model_metadata (model_type, model_name, last_trained, training_samples, accuracy, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [
            'ollama',
            settings.ollama_model or 'apex-trader',
            None,
            0,
            0.0,
            'Initial entry - not yet trained'
        ])
        
        log.info("✓ Initial model metadata inserted")
        
        # Create indexes for performance
        log.info("Creating indexes...")
        await store.execute_write("CREATE INDEX IF NOT EXISTS idx_llm_calls_timestamp ON llm_calls(timestamp)")
        await store.execute_write("CREATE INDEX IF NOT EXISTS idx_llm_calls_agent ON llm_calls(agent)")
        await store.execute_write("CREATE INDEX IF NOT EXISTS idx_bot_decisions_timestamp ON bot_decisions(timestamp)")
        await store.execute_write("CREATE INDEX IF NOT EXISTS idx_bot_decisions_symbol ON bot_decisions(symbol)")
        
        log.info("✓ Indexes created")
        
        # Verify tables exist
        tables = store.execute_read("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'main' 
            AND table_name IN ('llm_calls', 'bot_decisions', 'model_metadata')
        """)
        
        log.info("✓ Verified tables: {}", [t[0] for t in tables])
        
        await store.stop()
        
        log.info("✅ All tables created successfully!")
        log.info("")
        log.info("Next steps:")
        log.info("1. Restart your bot to start logging metrics")
        log.info("2. Open dashboard and check AI & MLOPS tab")
        log.info("3. Apex Trader health monitoring will show real data")
        
    except Exception as e:
        log.error("Failed to create tables: {}", e)
        import traceback
        traceback.print_exc()
        await store.stop()
        raise

if __name__ == "__main__":
    import asyncio
    asyncio.run(init_tables())

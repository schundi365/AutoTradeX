#!/usr/bin/env python3
"""
Test script to verify Apex Health logging is working.
"""
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from memory.duckdb_store import DuckDBStore
from core.config import settings
from core.logger import setup_logging, get_agent_logger

setup_logging()
log = get_agent_logger("TEST")

async def test_logging():
    """Test logging to apex health tables."""
    store = DuckDBStore(settings.training.duckdb_path)
    await store.start()
    
    try:
        # Test 1: Log an LLM call
        log.info("Test 1: Logging LLM call...")
        await store.execute_write("""
            INSERT INTO llm_calls 
            (timestamp, agent, tier, model, latency_ms, success, timeout, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [datetime.utcnow(), "test_agent", "ollama", "apex-trader", 150, 1, 0, 0])
        log.info("✓ LLM call logged")
        
        # Test 2: Log a bot decision
        log.info("Test 2: Logging bot decision...")
        await store.execute_write("""
            INSERT INTO bot_decisions 
            (timestamp, symbol, decision, confidence, outcome, decision_time_ms)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [datetime.utcnow(), "XAUUSD", "GO", 0.85, None, 250])
        log.info("✓ Bot decision logged")
        
        # Test 3: Read back the data
        log.info("Test 3: Reading back data...")
        llm_calls = store.execute_read("SELECT COUNT(*) FROM llm_calls")
        bot_decisions = store.execute_read("SELECT COUNT(*) FROM bot_decisions")
        
        log.info("✓ LLM calls in DB: {}", llm_calls[0][0])
        log.info("✓ Bot decisions in DB: {}", bot_decisions[0][0])
        
        # Test 4: Query latest entries
        log.info("Test 4: Querying latest entries...")
        latest_llm = store.execute_read("""
            SELECT timestamp, agent, tier, model, latency_ms 
            FROM llm_calls 
            ORDER BY timestamp DESC 
            LIMIT 1
        """)
        
        latest_decision = store.execute_read("""
            SELECT timestamp, symbol, decision, confidence, decision_time_ms 
            FROM bot_decisions 
            ORDER BY timestamp DESC 
            LIMIT 1
        """)
        
        if latest_llm:
            log.info("✓ Latest LLM call: {} | {} | {} | {}ms", 
                    latest_llm[0][1], latest_llm[0][2], latest_llm[0][3], latest_llm[0][4])
        
        if latest_decision:
            log.info("✓ Latest decision: {} | {} | confidence: {:.0%} | time: {}ms", 
                    latest_decision[0][1], latest_decision[0][2], latest_decision[0][3], latest_decision[0][4])
        
        await store.stop()
        
        log.info("")
        log.info("✅ All tests passed!")
        log.info("Apex Health logging is working correctly.")
        
    except Exception as e:
        log.error("Test failed: {}", e)
        import traceback
        traceback.print_exc()
        await store.stop()
        raise

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_logging())

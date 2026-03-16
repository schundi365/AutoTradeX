import asyncio
import json
from datetime import datetime
from memory.duckdb_store import DuckDBStore
from core.config import settings

async def test_sentiment_persistence():
    print("Testing Sentiment Persistence...")
    store = DuckDBStore(settings.training.duckdb_path)
    await store.start()
    
    # Initialize schema
    await store.init_schema()
    
    news_summary = "Test news summary for sentiment analysis."
    adjustments = [
        {"symbol": "AAPL", "boost": 0.05, "reasoning": "Strong iPhone sales reported."},
        {"symbol": "BTCUSD", "boost": -0.1, "reasoning": "Regulatory concerns in Asia."}
    ]
    
    print(f"Logging sentiment analysis for: {news_summary}")
    await store.log_sentiment_analysis(news_summary, adjustments)
    
    print("Reading back latest sentiment...")
    rows = store.execute_read(
        "SELECT timestamp, news_summary, adjustments_json FROM sentiment_analysis ORDER BY timestamp DESC LIMIT 1"
    )
    
    if not rows:
        print("FAIL: No rows found in sentiment_analysis table.")
        await store.stop()
        return

    ts, summary, adj_json = rows[0]
    print(f"Retrieved: {ts} | {summary}")
    print(f"Adjustments: {adj_json}")
    
    assert summary == news_summary
    assert json.loads(adj_json) == adjustments
    print("SUCCESS: Persistence verified.")
    
    await store.stop()

if __name__ == "__main__":
    asyncio.run(test_sentiment_persistence())

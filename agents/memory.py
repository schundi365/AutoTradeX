import chromadb
from chromadb.utils import embedding_functions
from datetime import datetime
from pathlib import Path
from core.logger import get_agent_logger

log = get_agent_logger("MEMORY")

class TradeMemory:
    """
    Long-term memory for the trading bot using ChromaDB.
    Stores 'contextual' snapshots of trades (indicators + news + macro)
    and their eventual outcomes to help the bot learn from the past.
    """
    def __init__(self, db_path: str = "data/chroma_db"):
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        self.client = chromadb.PersistentClient(path=str(self.db_path))
        self.collection = self.client.get_or_create_collection(
            name="news_geopolitical_events",
            metadata={"hnsw:space": "cosine"}
        )
        self.embed_fn = embedding_functions.DefaultEmbeddingFunction()

    def store_event_context(self, event_id: str, news_text: str, metadata: dict):
        """Stores a news or geopolitical event for future retrieval."""
        self.collection.add(
            ids=[event_id],
            documents=[news_text],
            metadatas=[metadata]
        )
        log.info("Memory: Stored news event context {}", event_id)

    def store_trade_context(self, trade_id: str, context_text: str, metadata: dict):
        """Stores the full context of a trade for future analysis/learning."""
        try:
            self.collection.add(
                ids=[trade_id],
                documents=[context_text],
                metadatas=[metadata]
            )
            log.info("Memory: Stored trade context for {}", trade_id)
        except Exception as e:
            log.warning("Memory: Failed to store trade context {}: {}", trade_id, e)

    def search_similar_events(self, news_query: str, n_results: int = 5) -> list[dict]:
        """Retrieves similar past news or geopolitical contexts."""
        try:
            results = self.collection.query(
                query_texts=[news_query],
                n_results=n_results
            )
            
            formatted = []
            if results and results['documents']:
                for i in range(len(results['documents'][0])):
                    formatted.append({
                        "context": results['documents'][0][i],
                        "metadata": results['metadatas'][0][i],
                        "distance": results['distances'][0][i]
                    })
            return formatted
        except Exception as e:
            log.warning("Memory: Search failed: {}", e)
            return []

memory = TradeMemory()

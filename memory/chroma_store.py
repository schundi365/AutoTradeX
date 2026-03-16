"""
APEX Bot — ChromaDB Store
News RAG and trade context memory.
Uses default sentence-transformers embeddings (no LLM API calls for embeddings).
"""
from __future__ import annotations
import json
from datetime import datetime
from typing import Optional

from loguru import logger as log


class ChromaStore:
    """
    Persistent ChromaDB store for:
      - apex_news        : news items → used by sentiment_agent for RAG
      - apex_trade_context: trade decisions + outcomes → used by orchestrator
    """

    def __init__(self, path: str = "data/chromadb"):
        self._path = path
        self._client = None
        self.news_collection = None
        self.trade_collection = None

    def connect(self):
        """Initialise ChromaDB client and collections. Call once at startup."""
        try:
            import chromadb
            self._client = chromadb.PersistentClient(path=self._path)

            self.news_collection = self._client.get_or_create_collection(
                name="apex_news",
                metadata={"hnsw:space": "cosine"},
            )
            self.trade_collection = self._client.get_or_create_collection(
                name="apex_trade_context",
                metadata={"hnsw:space": "cosine"},
            )
            log.info("ChromaDB connected: {} (news={} docs, trades={} docs)",
                     self._path,
                     self.news_collection.count(),
                     self.trade_collection.count())
        except ImportError:
            log.warning("chromadb not installed — RAG disabled. Run: pip install chromadb")
        except Exception as e:
            log.error("ChromaDB init failed: {}", e)

    # ── News RAG ──────────────────────────────────────────────────────────────

    def store_news(self, item) -> bool:
        """
        Embed and store a NewsItem in ChromaDB.
        item: NewsItem (core/models.py) or dict with id, title, summary, sentiment, impact
        """
        if not self.news_collection:
            return False
        try:
            # Support both Pydantic models and dicts
            if hasattr(item, "model_dump"):
                data = item.model_dump()
            else:
                data = dict(item)

            doc_id = str(data.get("id", ""))
            text = f"{data.get('title', '')} {data.get('summary', '')}"

            self.news_collection.upsert(
                ids=[doc_id],
                documents=[text],
                metadatas=[{
                    "id":        doc_id,
                    "title":     data.get("title", "")[:500],
                    "source":    data.get("source", ""),
                    "sentiment": float(data.get("sentiment", 0.0)),
                    "impact":    str(data.get("impact", "LOW")),
                    "symbols":   json.dumps(data.get("symbols", [])),
                    "published": str(data.get("published", datetime.utcnow())),
                }],
            )
            return True
        except Exception as e:
            log.error("ChromaDB store_news error: {}", e)
            return False

    def retrieve_similar_news(self, query_text: str, n: int = 5) -> list[dict]:
        """
        Find the n most similar past news events by semantic similarity.
        Returns list of metadata dicts (each has title, sentiment, impact, etc.)
        """
        if not self.news_collection or self.news_collection.count() == 0:
            return []
        try:
            results = self.news_collection.query(
                query_texts=[query_text],
                n_results=min(n, self.news_collection.count()),
                include=["metadatas", "distances"],
            )
            items = []
            for meta, dist in zip(
                results["metadatas"][0], results["distances"][0]
            ):
                meta["similarity"] = round(1.0 - dist, 4)
                items.append(meta)
            return items
        except Exception as e:
            log.error("ChromaDB retrieve_similar_news error: {}", e)
            return []

    def get_sentiment_context(self, symbol: str, n: int = 5) -> dict:
        """
        Retrieve recent sentiment context for a given symbol.
        Returns aggregated sentiment and top news snippets.
        """
        query = f"{symbol} trading news market sentiment"
        items = self.retrieve_similar_news(query, n=n)
        if not items:
            return {"avg_sentiment": 0.0, "count": 0, "items": []}

        sentiments = [i.get("sentiment", 0.0) for i in items]
        avg = sum(sentiments) / len(sentiments) if sentiments else 0.0
        return {
            "avg_sentiment": round(avg, 4),
            "count": len(items),
            "items": items,
        }

    # ── Trade context RAG ─────────────────────────────────────────────────────

    def store_trade_context(
        self,
        trade,
        reasoning: str,
        news_summary: str,
        outcome: Optional[str] = None,
        final_pnl: Optional[float] = None,
    ) -> bool:
        """
        Store the full context of a trade decision for future learning.
        trade: Trade model or dict
        """
        if not self.trade_collection:
            return False
        try:
            if hasattr(trade, "model_dump"):
                data = trade.model_dump()
            else:
                data = dict(trade)

            trade_id = str(data.get("id", ""))
            document = (
                f"Symbol: {data.get('symbol')} | Direction: {data.get('direction')} | "
                f"Strategy: {data.get('strategy')} | "
                f"Reasoning: {reasoning[:500]} | "
                f"News: {news_summary[:300]}"
            )
            metadata = {
                "trade_id":   trade_id,
                "symbol":     str(data.get("symbol", "")),
                "direction":  str(data.get("direction", "")),
                "strategy":   str(data.get("strategy", "")),
                "entry":      float(data.get("entry_price", 0.0)),
                "sl":         float(data.get("stop_loss", 0.0)),
                "tp":         float(data.get("take_profit", 0.0)),
                "outcome":    str(outcome or "PENDING"),
                "final_pnl":  float(final_pnl or 0.0),
                "timestamp":  str(datetime.utcnow()),
            }
            self.trade_collection.upsert(
                ids=[trade_id],
                documents=[document],
                metadatas=[metadata],
            )
            return True
        except Exception as e:
            log.error("ChromaDB store_trade_context error: {}", e)
            return False

    def retrieve_similar_trades(self, signal, n: int = 3) -> list[dict]:
        """
        Find n similar past trade setups and their outcomes.
        signal: TradingSignal model or dict with symbol, direction, strategy fields.
        Returns list of trade metadata dicts.
        """
        if not self.trade_collection or self.trade_collection.count() == 0:
            return []
        try:
            if hasattr(signal, "model_dump"):
                data = signal.model_dump()
            else:
                data = dict(signal)

            query = (
                f"Symbol: {data.get('symbol')} | Direction: {data.get('direction')} | "
                f"Strategy: {data.get('strategy')}"
            )
            results = self.trade_collection.query(
                query_texts=[query],
                n_results=min(n, self.trade_collection.count()),
                include=["metadatas", "distances"],
            )
            items = []
            for meta, dist in zip(
                results["metadatas"][0], results["distances"][0]
            ):
                meta["similarity"] = round(1.0 - dist, 4)
                items.append(meta)
            return items
        except Exception as e:
            log.error("ChromaDB retrieve_similar_trades error: {}", e)
            return []

    def update_trade_outcome(self, trade_id: str, outcome: str, final_pnl: float):
        """Update the outcome of a stored trade context when the trade closes."""
        if not self.trade_collection:
            return
        try:
            existing = self.trade_collection.get(ids=[trade_id], include=["metadatas", "documents"])
            if not existing["ids"]:
                return
            meta = existing["metadatas"][0]
            meta["outcome"] = outcome
            meta["final_pnl"] = final_pnl
            self.trade_collection.update(
                ids=[trade_id],
                metadatas=[meta],
            )
        except Exception as e:
            log.error("ChromaDB update_trade_outcome error: {}", e)

    # ── Utilities ─────────────────────────────────────────────────────────────

    def news_count(self) -> int:
        return self.news_collection.count() if self.news_collection else 0

    def trade_count(self) -> int:
        return self.trade_collection.count() if self.trade_collection else 0

    def clear_news(self):
        """Wipe news collection (useful for testing)."""
        if self.news_collection:
            self._client.delete_collection("apex_news")
            self.news_collection = self._client.create_collection(
                "apex_news", metadata={"hnsw:space": "cosine"}
            )
            log.warning("ChromaDB apex_news collection cleared")

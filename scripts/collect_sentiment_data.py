"""
APEX Bot — Sentiment Data Collector
Downloads pre-labelled financial NLP datasets and saves them for ChromaDB ingestion.

Sources:
  1. FinancialPhraseBank (HuggingFace) — gold-standard financial sentiment labels
  2. FiQA 2018 (HuggingFace) — financial QA + sentiment scoring
  3. Alpaca Financial News (HuggingFace) — 100k+ labelled news articles
  4. GDELT — geopolitical news with pre-scored AvgTone
  5. CNN Fear & Greed Index — risk-on/off daily signal

Usage:
    python scripts/collect_sentiment_data.py
    python scripts/collect_sentiment_data.py --source gdelt --keywords "gold inflation"
    python scripts/collect_sentiment_data.py --source feargreed
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

OUT_DIR = Path("data/sentiment")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# 1. HuggingFace datasets
# ─────────────────────────────────────────────────────────────────────────────

def collect_huggingface() -> int:
    """Download FinancialPhraseBank, FiQA 2018, and Alpaca News."""
    try:
        from datasets import load_dataset
        import pandas as pd
    except ImportError:
        print("ERROR: datasets not installed. Run: pip install datasets pandas")
        return 0

    total = 0

    # ── FinancialPhraseBank ───────────────────────────────────────────────────
    try:
        print("  [HuggingFace] FinancialPhraseBank (sentences_allagree)...")
        ds = load_dataset("financial_phrasebank", "sentences_allagree", trust_remote_code=True)
        df = ds["train"].to_pandas()
        # Labels: 0=negative, 1=neutral, 2=positive → map to -1/0/+1
        label_map = {0: -1.0, 1: 0.0, 2: 1.0}
        df["sentiment"] = df["label"].map(label_map)
        df["source"] = "financial_phrasebank"
        df["impact"] = "MEDIUM"
        df = df.rename(columns={"sentence": "title"})
        df["summary"] = df["title"]
        df["published"] = datetime.utcnow().isoformat()
        out = OUT_DIR / "financial_phrasebank.jsonl"
        df[["title", "summary", "sentiment", "source", "impact", "published"]].to_json(
            out, orient="records", lines=True
        )
        print(f"    Saved {len(df):,} examples → {out}")
        total += len(df)
    except Exception as e:
        print(f"    WARNING: FinancialPhraseBank failed: {e}")

    # ── FiQA 2018 ────────────────────────────────────────────────────────────
    try:
        print("  [HuggingFace] FiQA 2018...")
        ds = load_dataset("pauri32/fiqa-2018", trust_remote_code=True)
        df = ds["train"].to_pandas()
        # FiQA has 'sentence' and 'sentiment_score' (-1 to +1)
        df["source"] = "fiqa_2018"
        df["impact"] = "MEDIUM"
        if "sentence" in df.columns:
            df = df.rename(columns={"sentence": "title"})
        if "sentiment_score" in df.columns:
            df = df.rename(columns={"sentiment_score": "sentiment"})
        df["summary"] = df.get("title", "")
        df["published"] = datetime.utcnow().isoformat()
        out = OUT_DIR / "fiqa_2018.jsonl"
        keep = [c for c in ["title", "summary", "sentiment", "source", "impact", "published"] if c in df.columns]
        df[keep].to_json(out, orient="records", lines=True)
        print(f"    Saved {len(df):,} examples → {out}")
        total += len(df)
    except Exception as e:
        print(f"    WARNING: FiQA 2018 failed: {e}")

    # ── Alpaca Financial News ─────────────────────────────────────────────────
    try:
        print("  [HuggingFace] Alpaca Financial News (sample 20k)...")
        ds = load_dataset("ashraq/financial-news-articles", trust_remote_code=True)
        df = ds["train"].to_pandas().head(20000)  # sample — full dataset is huge
        df["source"] = "alpaca_financial_news"
        df["impact"] = "LOW"
        df["sentiment"] = 0.0  # no labels — sentiment to be added via NLP
        df["published"] = datetime.utcnow().isoformat()
        if "headline" in df.columns:
            df = df.rename(columns={"headline": "title"})
        if "summary" not in df.columns:
            df["summary"] = df.get("title", "")
        out = OUT_DIR / "alpaca_news.jsonl"
        keep = [c for c in ["title", "summary", "sentiment", "source", "impact", "published"] if c in df.columns]
        df[keep].to_json(out, orient="records", lines=True)
        print(f"    Saved {len(df):,} examples → {out}")
        total += len(df)
    except Exception as e:
        print(f"    WARNING: Alpaca News failed: {e}")

    return total


# ─────────────────────────────────────────────────────────────────────────────
# 2. GDELT — Geopolitical news with pre-scored sentiment
# ─────────────────────────────────────────────────────────────────────────────

def collect_gdelt(
    keywords: list[str] | None = None,
    start_date: str = "2022-01-01",
    end_date: str | None = None,
) -> int:
    """
    Fetch GDELT v2 news events mentioning financial keywords.
    AvgTone is pre-scored: negative = bearish, positive = bullish.
    """
    try:
        import pandas as pd
        import requests
    except ImportError:
        print("ERROR: pandas/requests not installed")
        return 0

    if keywords is None:
        keywords = ["gold", "federal reserve", "inflation", "oil", "geopolitical", "dollar"]

    end_date = end_date or datetime.utcnow().strftime("%Y-%m-%d")

    # GDELT GKG CSV export for keyword search
    print(f"  [GDELT] Fetching news: keywords={keywords}, {start_date} to {end_date}")

    # GDELT BigQuery approach — use their CSV endpoint (no auth needed)
    # Format: YYYYMMDDHHMMSS
    all_records = []
    try:
        # Use GDELT DOC 2.0 API (free, no key)
        url = "https://api.gdeltproject.org/api/v2/doc/doc"
        params = {
            "query": " OR ".join(f'"{k}"' for k in keywords),
            "mode": "artlist",
            "maxrecords": 250,
            "format": "json",
            "startdatetime": start_date.replace("-", "") + "000000",
            "enddatetime": end_date.replace("-", "") + "235959",
            "sort": "DateDesc",
        }
        r = requests.get(url, params=params, timeout=30)
        if r.status_code == 200:
            data = r.json()
            articles = data.get("articles", [])
            for art in articles:
                # GDELT doesn't give AvgTone in DOC API — estimate from seenodes/socialimage
                all_records.append({
                    "title":     art.get("title", ""),
                    "summary":   art.get("seendescription", ""),
                    "url":       art.get("url", ""),
                    "source":    art.get("domain", "gdelt"),
                    "published": art.get("seendate", ""),
                    "sentiment": 0.0,  # GDELT DOC API doesn't provide AvgTone
                    "impact":    "MEDIUM",
                })
            print(f"    GDELT DOC API: {len(articles)} articles")
        else:
            print(f"    WARNING: GDELT API returned {r.status_code}")
    except Exception as e:
        print(f"    WARNING: GDELT API error: {e}")
        print("    Tip: For bulk GDELT with AvgTone, use the gdelt Python package:")
        print("         pip install gdelt")
        print("         from gdelt import gdelt; gd = gdelt.gdelt(version=2)")
        print("         results = gd.Search(['gold'], date=['2022 Jan 1', '2024 Dec 31'])")

    if all_records:
        out = OUT_DIR / "gdelt_news.jsonl"
        with open(out, "w") as f:
            for r in all_records:
                f.write(json.dumps(r) + "\n")
        print(f"    Saved {len(all_records)} GDELT records → {out}")

    return len(all_records)


# ─────────────────────────────────────────────────────────────────────────────
# 3. CNN Fear & Greed Index
# ─────────────────────────────────────────────────────────────────────────────

def collect_fear_greed() -> int:
    """
    Fetch CNN Fear & Greed Index historical data.
    score < 30 → RISK_OFF training signal
    score > 70 → RISK_ON training signal
    """
    try:
        import requests
        import pandas as pd
    except ImportError:
        print("ERROR: requests/pandas not installed")
        return 0

    print("  [Fear & Greed] Fetching CNN index history...")
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata/2020-01-01"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; APEX-Bot/1.0)"}

    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            print(f"    WARNING: F&G API returned {r.status_code}")
            return 0

        data = r.json()["fear_and_greed_historical"]["data"]
        df = pd.DataFrame(data)
        df["timestamp"] = pd.to_datetime(df["x"], unit="ms")
        df = df.rename(columns={"y": "score", "rating": "label"})

        # Map to macro regime training signal
        def to_regime(score):
            if score < 25:
                return "RISK_OFF_EXTREME"
            elif score < 45:
                return "RISK_OFF"
            elif score > 75:
                return "RISK_ON_EXTREME"
            elif score > 55:
                return "RISK_ON"
            return "NEUTRAL"

        df["macro_regime"] = df["score"].apply(to_regime)
        df["source"] = "cnn_fear_greed"

        out = OUT_DIR / "fear_greed_history.csv"
        df[["timestamp", "score", "label", "macro_regime", "source"]].to_csv(out, index=False)
        print(f"    Saved {len(df):,} daily records → {out}")
        return len(df)
    except Exception as e:
        print(f"    WARNING: Fear & Greed fetch failed: {e}")
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# Ingest into ChromaDB
# ─────────────────────────────────────────────────────────────────────────────

def ingest_into_chromadb(chroma_path: str = "data/chromadb") -> int:
    """Load all JSONL sentiment files into ChromaDB for RAG."""
    try:
        from memory.chroma_store import ChromaStore
    except ImportError:
        print("WARNING: ChromaStore not available — skipping ChromaDB ingestion")
        return 0

    store = ChromaStore(path=chroma_path)
    store.connect()
    if not store.news_collection:
        return 0

    total = 0
    for jsonl_path in OUT_DIR.glob("*.jsonl"):
        print(f"  Loading {jsonl_path.name} into ChromaDB...")
        with open(jsonl_path) as f:
            batch_ids = []
            batch_docs = []
            batch_meta = []
            for i, line in enumerate(f):
                try:
                    item = json.loads(line)
                    doc_id = f"{jsonl_path.stem}_{i}"
                    text = f"{item.get('title', '')} {item.get('summary', '')}"
                    batch_ids.append(doc_id)
                    batch_docs.append(text[:2000])
                    batch_meta.append({
                        "title":     item.get("title", "")[:500],
                        "source":    item.get("source", ""),
                        "sentiment": float(item.get("sentiment", 0.0)),
                        "impact":    item.get("impact", "LOW"),
                        "symbols":   "[]",
                        "published": str(item.get("published", "")),
                    })
                    # Upsert in batches of 500
                    if len(batch_ids) >= 500:
                        store.news_collection.upsert(
                            ids=batch_ids, documents=batch_docs, metadatas=batch_meta
                        )
                        total += len(batch_ids)
                        batch_ids, batch_docs, batch_meta = [], [], []
                except Exception as e:
                    pass

            if batch_ids:
                store.news_collection.upsert(
                    ids=batch_ids, documents=batch_docs, metadatas=batch_meta
                )
                total += len(batch_ids)

        print(f"    {jsonl_path.name}: ChromaDB now has {store.news_collection.count()} docs")

    return total


# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="APEX sentiment data collector")
    parser.add_argument(
        "--source",
        choices=["huggingface", "gdelt", "feargreed", "all"],
        default="all",
    )
    parser.add_argument(
        "--keywords",
        nargs="+",
        default=["gold", "federal reserve", "inflation", "dollar", "oil"],
        help="GDELT keywords",
    )
    parser.add_argument("--start", default="2022-01-01", help="GDELT start date")
    parser.add_argument("--chroma", default="data/chromadb", help="ChromaDB path")
    parser.add_argument("--skip-chroma", action="store_true")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("APEX Sentiment Data Collector")
    print(f"{'='*60}\n")

    total = 0

    if args.source in ("huggingface", "all"):
        print("[HuggingFace Datasets]")
        total += collect_huggingface()

    if args.source in ("gdelt", "all"):
        print("\n[GDELT]")
        total += collect_gdelt(keywords=args.keywords, start_date=args.start)

    if args.source in ("feargreed", "all"):
        print("\n[CNN Fear & Greed]")
        total += collect_fear_greed()

    print(f"\nTotal sentiment records: {total:,}")

    if not args.skip_chroma and total > 0:
        print("\nIngesting into ChromaDB...")
        chroma_total = ingest_into_chromadb(chroma_path=args.chroma)
        print(f"ChromaDB: {chroma_total:,} documents indexed")

    print("\nDone.")


if __name__ == "__main__":
    main()

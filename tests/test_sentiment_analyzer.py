"""
Unit tests for SentimentAnalyzer.

Tests specific examples, edge cases, and error conditions for sentiment analysis.
"""
import pytest
import asyncio
from datetime import datetime
import uuid

from data.collectors import (
    SentimentAnalyzer,
    NewsArticle,
    SentimentResult,
    EntityType,
    NewsCategory,
)
from data.event_bus import EventBus, EventType


@pytest.fixture
def sentiment_analyzer():
    """Create a SentimentAnalyzer instance"""
    return SentimentAnalyzer()


@pytest.fixture
def sentiment_analyzer_with_bus():
    """Create a SentimentAnalyzer with event bus"""
    event_bus = EventBus()
    analyzer = SentimentAnalyzer(event_bus=event_bus)
    return analyzer, event_bus


def test_sentiment_analyzer_initialization():
    """Test that SentimentAnalyzer initializes correctly"""
    analyzer = SentimentAnalyzer()
    assert analyzer is not None
    assert analyzer.event_bus is None
    assert analyzer._entity_patterns is not None
    assert analyzer._category_keywords is not None


@pytest.mark.asyncio
async def test_analyze_positive_news(sentiment_analyzer):
    """Test sentiment analysis of positive news"""
    article = NewsArticle(
        article_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        title="Gold Prices Surge to Record High",
        content="Gold prices jumped 3% today, reaching a new record high as investors "
                "rally behind the precious metal amid strong demand.",
        source="Reuters",
    )
    
    result = await sentiment_analyzer.analyze_news(article)
    
    assert result.sentiment_score > 0.0, "Positive news should have positive sentiment"
    assert result.article_id == article.article_id
    assert result.title == article.title
    assert result.confidence > 0.0


@pytest.mark.asyncio
async def test_analyze_negative_news(sentiment_analyzer):
    """Test sentiment analysis of negative news"""
    article = NewsArticle(
        article_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        title="Oil Prices Crash on Recession Fears",
        content="Crude oil prices plunged 5% today as recession fears and weak demand "
                "triggered a massive sell-off in energy markets.",
        source="Bloomberg",
    )
    
    result = await sentiment_analyzer.analyze_news(article)
    
    assert result.sentiment_score < 0.0, "Negative news should have negative sentiment"
    assert result.article_id == article.article_id


@pytest.mark.asyncio
async def test_analyze_neutral_news(sentiment_analyzer):
    """Test sentiment analysis of neutral news"""
    article = NewsArticle(
        article_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        title="Market Update",
        content="The market opened today with trading activity across various sectors.",
        source="Financial Times",
    )
    
    result = await sentiment_analyzer.analyze_news(article)
    
    assert abs(result.sentiment_score) < 0.3, "Neutral news should have near-zero sentiment"


@pytest.mark.asyncio
async def test_analyze_empty_article(sentiment_analyzer):
    """Test sentiment analyzer handles empty articles gracefully"""
    article = NewsArticle(
        article_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        title="",
        content="",
        source="Test",
    )
    
    result = await sentiment_analyzer.analyze_news(article)
    
    assert result.sentiment_score == 0.0
    assert result.relevance_score == 0.0
    assert len(result.entities) == 0


def test_extract_currency_entities(sentiment_analyzer):
    """Test extraction of currency entities"""
    text = "The USD strengthened against EUR and GBP today."
    
    entities = sentiment_analyzer.extract_entities(text)
    
    currency_entities = [e for e in entities if e.type == EntityType.CURRENCY]
    assert len(currency_entities) >= 2, "Should extract USD, EUR, GBP"
    
    entity_texts = [e.text for e in currency_entities]
    assert 'USD' in entity_texts or 'Dollar' in entity_texts
    assert 'EUR' in entity_texts or 'Euro' in entity_texts


def test_extract_commodity_entities(sentiment_analyzer):
    """Test extraction of commodity entities"""
    text = "Gold and Silver prices rose while Oil declined."
    
    entities = sentiment_analyzer.extract_entities(text)
    
    commodity_entities = [e for e in entities if e.type == EntityType.COMMODITY]
    assert len(commodity_entities) >= 2, "Should extract Gold, Silver, Oil"
    
    entity_texts = [e.text for e in commodity_entities]
    assert 'Gold' in entity_texts
    assert 'Silver' in entity_texts or 'Oil' in entity_texts


def test_extract_central_bank_entities(sentiment_analyzer):
    """Test extraction of central bank entities"""
    text = "The Federal Reserve and ECB announced policy decisions."
    
    entities = sentiment_analyzer.extract_entities(text)
    
    bank_entities = [e for e in entities if e.type == EntityType.CENTRAL_BANK]
    assert len(bank_entities) >= 2, "Should extract Fed and ECB"


def test_classify_earnings_category(sentiment_analyzer):
    """Test classification of earnings news"""
    article = NewsArticle(
        article_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        title="Company Reports Strong Quarterly Earnings",
        content="The company beat earnings estimates with revenue growth of 15%.",
        source="Test",
    )
    
    category = sentiment_analyzer.classify_category(article)
    
    assert category == NewsCategory.EARNINGS


def test_classify_economic_data_category(sentiment_analyzer):
    """Test classification of economic data news"""
    article = NewsArticle(
        article_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        title="GDP Growth Exceeds Expectations",
        content="The economy grew 3.2% in Q4, beating forecasts as inflation cooled.",
        source="Test",
    )
    
    category = sentiment_analyzer.classify_category(article)
    
    assert category == NewsCategory.ECONOMIC_DATA


def test_classify_geopolitical_category(sentiment_analyzer):
    """Test classification of geopolitical news"""
    article = NewsArticle(
        article_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        title="Trade War Tensions Escalate",
        content="New tariffs announced as trade war tensions between nations escalate.",
        source="Test",
    )
    
    category = sentiment_analyzer.classify_category(article)
    
    assert category == NewsCategory.GEOPOLITICAL


def test_classify_regulatory_category(sentiment_analyzer):
    """Test classification of regulatory news"""
    article = NewsArticle(
        article_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        title="SEC Announces New Regulations",
        content="The SEC approved new compliance rules for financial institutions.",
        source="Test",
    )
    
    category = sentiment_analyzer.classify_category(article)
    
    assert category == NewsCategory.REGULATORY


def test_high_impact_detection(sentiment_analyzer):
    """Test detection of high-impact news"""
    # Create result with high sentiment
    result = SentimentResult(
        article_id="test",
        timestamp=datetime.utcnow(),
        title="Test",
        content="Test",
        source="Test",
        sentiment_score=0.85,  # > 0.7 threshold
        relevance_score=0.9,
        confidence=0.9,
    )
    
    assert result.is_high_impact is True
    
    # Create result with low sentiment
    result_low = SentimentResult(
        article_id="test",
        timestamp=datetime.utcnow(),
        title="Test",
        content="Test",
        source="Test",
        sentiment_score=0.5,  # < 0.7 threshold
        relevance_score=0.9,
        confidence=0.9,
    )
    
    assert result_low.is_high_impact is False


def test_high_impact_negative_sentiment(sentiment_analyzer):
    """Test high-impact detection with negative sentiment"""
    result = SentimentResult(
        article_id="test",
        timestamp=datetime.utcnow(),
        title="Test",
        content="Test",
        source="Test",
        sentiment_score=-0.85,  # |sentiment| > 0.7
        relevance_score=0.9,
        confidence=0.9,
    )
    
    assert result.is_high_impact is True


@pytest.mark.asyncio
async def test_high_impact_event_emission(sentiment_analyzer_with_bus):
    """Test that high-impact news emits event to event bus"""
    analyzer, event_bus = sentiment_analyzer_with_bus
    
    # Start event bus
    await event_bus.start()
    
    # Track emitted events
    emitted_events = []
    
    async def capture_event(event):
        emitted_events.append(event)
    
    await event_bus.subscribe(EventType.HIGH_IMPACT_NEWS, capture_event)
    
    # Analyze high-impact article
    article = NewsArticle(
        article_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        title="Market Crashes on Crisis",
        content="Markets plunged dramatically as crisis fears triggered massive sell-off "
                "with prices tumbling and investors fleeing to safety.",
        source="Test",
    )
    
    result = await analyzer.analyze_news(article)
    
    # Wait for event processing
    await asyncio.sleep(0.1)
    
    # Stop event bus
    await event_bus.stop()
    
    # Verify event was emitted if sentiment is high enough
    if result.is_high_impact:
        assert len(emitted_events) > 0, "High-impact event should be emitted"
        assert emitted_events[0].type == EventType.HIGH_IMPACT_NEWS


def test_map_entities_to_symbols(sentiment_analyzer):
    """Test mapping of entities to trading symbols"""
    text = "Gold prices rose while EUR weakened against USD."
    
    entities = sentiment_analyzer.extract_entities(text)
    symbols = sentiment_analyzer._map_to_symbols(entities)
    
    assert 'XAUUSD' in symbols, "Gold should map to XAUUSD"
    assert 'EURUSD' in symbols, "EUR should map to EURUSD"


def test_relevance_score_calculation(sentiment_analyzer):
    """Test relevance score calculation"""
    # High relevance text
    high_relevance = "Gold market trading shows strong price movement in forex currency."
    entities_high = sentiment_analyzer.extract_entities(high_relevance)
    relevance_high = sentiment_analyzer._compute_relevance(high_relevance, entities_high)
    
    # Low relevance text
    low_relevance = "The weather is nice today."
    entities_low = sentiment_analyzer.extract_entities(low_relevance)
    relevance_low = sentiment_analyzer._compute_relevance(low_relevance, entities_low)
    
    assert relevance_high > relevance_low, "Financial text should have higher relevance"
    assert 0.0 <= relevance_high <= 1.0, "Relevance should be in [0, 1]"
    assert 0.0 <= relevance_low <= 1.0, "Relevance should be in [0, 1]"


@pytest.mark.asyncio
async def test_processing_time_under_5_seconds(sentiment_analyzer):
    """Test that sentiment analysis completes within 5 seconds"""
    article = NewsArticle(
        article_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        title="Market Update with Multiple Entities",
        content="Gold, Silver, Oil, EUR, USD, GBP, JPY, Federal Reserve, ECB, "
                "earnings, GDP, inflation, trade war, regulations, and more news.",
        source="Test",
    )
    
    start_time = datetime.utcnow()
    result = await sentiment_analyzer.analyze_news(article)
    end_time = datetime.utcnow()
    
    processing_time = (end_time - start_time).total_seconds()
    
    assert processing_time < 5.0, f"Processing took {processing_time}s, should be < 5s"
    assert result is not None


def test_sentiment_result_to_dict(sentiment_analyzer):
    """Test SentimentResult serialization to dictionary"""
    result = SentimentResult(
        article_id="test123",
        timestamp=datetime.utcnow(),
        title="Test Title",
        content="Test Content",
        source="Test Source",
        sentiment_score=0.75,
        relevance_score=0.85,
        confidence=0.90,
        category=NewsCategory.EARNINGS,
        affected_symbols=['XAUUSD', 'EURUSD'],
    )
    
    result_dict = result.to_dict()
    
    assert result_dict['article_id'] == "test123"
    assert result_dict['sentiment_score'] == 0.75
    assert result_dict['relevance_score'] == 0.85
    assert result_dict['confidence'] == 0.90
    assert result_dict['category'] == 'EARNINGS'
    assert result_dict['affected_symbols'] == ['XAUUSD', 'EURUSD']

"""
Unit tests for Trade Journal
"""
import pytest
import tempfile
import os
from datetime import datetime, timedelta
from pathlib import Path

from data.trade_journal import (
    TradeJournal,
    TradeJournalEntry,
    DecisionType,
    DecisionMaker
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    # Create a temporary directory and file path (don't create the file yet)
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'test_journal.duckdb')
    
    yield db_path
    
    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)
    if os.path.exists(temp_dir):
        os.rmdir(temp_dir)


@pytest.fixture
def journal(temp_db):
    """Create a TradeJournal instance with temporary database"""
    return TradeJournal(db_path=temp_db)


def test_trade_journal_initialization(journal):
    """Test that trade journal initializes correctly"""
    assert journal.db_path.exists()


def test_record_signal_generated_decision(journal):
    """Test recording a signal generated decision"""
    entry = TradeJournalEntry(
        entry_id="test_001",
        timestamp=datetime.utcnow(),
        decision_type=DecisionType.SIGNAL_GENERATED,
        symbol="XAUUSD",
        direction="LONG",
        market_regime="TRENDING",
        risk_appetite="MODERATE",
        liquidity_conditions="GOOD",
        is_news_blackout=False,
        signal_score=7.5,
        confidence=0.75,
        risk_reward=2.5,
        indicators={"rsi": 65.0, "adx": 28.5, "atr": 1.2},
        decision="GO",
        reasoning="Strong trend with good momentum",
        decision_maker=DecisionMaker.FAST_PATH
    )
    
    journal.record_decision(entry)
    
    # Verify it was stored
    retrieved = journal.get_decision_by_id("test_001")
    assert retrieved is not None
    assert retrieved['symbol'] == "XAUUSD"
    assert retrieved['decision'] == "GO"
    assert retrieved['signal_score'] == 7.5


def test_record_decision_with_ml_predictions(journal):
    """Test recording a decision with ML predictions"""
    entry = TradeJournalEntry(
        entry_id="test_002",
        timestamp=datetime.utcnow(),
        decision_type=DecisionType.SIGNAL_APPROVED,
        symbol="EURUSD",
        direction="SHORT",
        market_regime="RANGING",
        risk_appetite="CONSERVATIVE",
        liquidity_conditions="EXCELLENT",
        is_news_blackout=False,
        signal_score=8.2,
        confidence=0.85,
        risk_reward=3.0,
        indicators={"rsi": 35.0, "macd": -0.5},
        ml_prediction=0.72,
        ml_confidence=0.80,
        model_id="xgboost_v1_20240101",
        decision="GO",
        reasoning="ML model confirms bearish signal",
        decision_maker=DecisionMaker.LLM
    )
    
    journal.record_decision(entry)
    
    # Verify ML fields were stored
    retrieved = journal.get_decision_by_id("test_002")
    assert retrieved['ml_prediction'] == 0.72
    assert retrieved['ml_confidence'] == 0.80
    assert retrieved['model_id'] == "xgboost_v1_20240101"


def test_link_outcome_to_decision(journal):
    """Test linking trade outcome to decision"""
    # First record a decision
    entry = TradeJournalEntry(
        entry_id="test_003",
        timestamp=datetime.utcnow(),
        decision_type=DecisionType.TRADE_OPENED,
        symbol="BTCUSD",
        direction="LONG",
        market_regime="VOLATILE",
        risk_appetite="AGGRESSIVE",
        liquidity_conditions="GOOD",
        is_news_blackout=False,
        signal_score=7.0,
        confidence=0.70,
        risk_reward=2.0,
        indicators={"rsi": 55.0},
        decision="GO",
        reasoning="Breakout confirmed",
        decision_maker=DecisionMaker.FAST_PATH,
        trade_id="trade_123"
    )
    
    journal.record_decision(entry)
    
    # Link outcome
    journal.link_outcome(
        trade_id="trade_123",
        entry_price=50000.0,
        exit_price=51000.0,
        pnl=1000.0,
        holding_time_seconds=3600,
        exit_reason="TAKE_PROFIT"
    )
    
    # Verify outcome was linked
    retrieved = journal.get_decision_by_id("test_003")
    assert retrieved['entry_price'] == 50000.0
    assert retrieved['exit_price'] == 51000.0
    assert retrieved['pnl'] == 1000.0
    assert retrieved['holding_time_seconds'] == 3600
    assert retrieved['exit_reason'] == "TAKE_PROFIT"


def test_get_decision_history_with_filters(journal):
    """Test querying decision history with various filters"""
    # Record multiple decisions
    now = datetime.utcnow()
    
    entries = [
        TradeJournalEntry(
            entry_id=f"test_{i:03d}",
            timestamp=now - timedelta(hours=i),
            decision_type=DecisionType.SIGNAL_GENERATED,
            symbol="XAUUSD" if i % 2 == 0 else "EURUSD",
            direction="LONG",
            market_regime="TRENDING",
            risk_appetite="MODERATE",
            liquidity_conditions="GOOD",
            is_news_blackout=False,
            signal_score=7.0 + i * 0.1,
            confidence=0.70,
            risk_reward=2.0,
            indicators={"rsi": 60.0},
            decision="GO" if i % 3 == 0 else "NOGO",
            reasoning="Test entry",
            decision_maker=DecisionMaker.FAST_PATH if i % 2 == 0 else DecisionMaker.LLM
        )
        for i in range(10)
    ]
    
    for entry in entries:
        journal.record_decision(entry)
    
    # Test symbol filter
    xauusd_decisions = journal.get_decision_history(symbol="XAUUSD")
    assert len(xauusd_decisions) == 5
    assert all(xauusd_decisions['symbol'] == "XAUUSD")
    
    # Test decision filter
    go_decisions = journal.get_decision_history(decision="GO")
    assert all(go_decisions['decision'] == "GO")
    
    # Test decision maker filter
    fast_path_decisions = journal.get_decision_history(
        decision_maker=DecisionMaker.FAST_PATH
    )
    assert all(fast_path_decisions['decision_maker'] == "FAST_PATH")
    
    # Test date range filter
    recent_decisions = journal.get_decision_history(
        start_date=now - timedelta(hours=5),
        end_date=now
    )
    assert len(recent_decisions) <= 6


def test_get_decisions_by_trade_id(journal):
    """Test retrieving all decisions related to a trade"""
    trade_id = "trade_456"
    
    # Record multiple decisions for same trade
    decisions = [
        TradeJournalEntry(
            entry_id=f"test_trade_{i}",
            timestamp=datetime.utcnow() + timedelta(seconds=i),
            decision_type=DecisionType.SIGNAL_GENERATED if i == 0 else DecisionType.TRADE_OPENED,
            symbol="XAUUSD",
            direction="LONG",
            market_regime="TRENDING",
            risk_appetite="MODERATE",
            liquidity_conditions="GOOD",
            is_news_blackout=False,
            signal_score=7.5,
            confidence=0.75,
            risk_reward=2.5,
            indicators={"rsi": 65.0},
            decision="GO",
            reasoning=f"Step {i}",
            decision_maker=DecisionMaker.FAST_PATH,
            trade_id=trade_id
        )
        for i in range(3)
    ]
    
    for decision in decisions:
        journal.record_decision(decision)
    
    # Retrieve all decisions for this trade
    trade_decisions = journal.get_decisions_by_trade_id(trade_id)
    assert len(trade_decisions) == 3
    assert all(trade_decisions['trade_id'] == trade_id)


def test_get_performance_by_decision_maker(journal):
    """Test performance breakdown by decision maker"""
    # Record decisions with outcomes
    entries = [
        # Fast path wins
        TradeJournalEntry(
            entry_id="fp_win_1",
            timestamp=datetime.utcnow(),
            decision_type=DecisionType.TRADE_CLOSED,
            symbol="XAUUSD",
            direction="LONG",
            market_regime="TRENDING",
            risk_appetite="MODERATE",
            liquidity_conditions="GOOD",
            is_news_blackout=False,
            signal_score=7.5,
            confidence=0.75,
            risk_reward=2.5,
            indicators={"rsi": 65.0},
            decision="GO",
            reasoning="Fast path win",
            decision_maker=DecisionMaker.FAST_PATH,
            trade_id="fp_1",
            pnl=100.0,
            holding_time_seconds=3600
        ),
        # Fast path loss
        TradeJournalEntry(
            entry_id="fp_loss_1",
            timestamp=datetime.utcnow(),
            decision_type=DecisionType.TRADE_CLOSED,
            symbol="EURUSD",
            direction="SHORT",
            market_regime="RANGING",
            risk_appetite="MODERATE",
            liquidity_conditions="GOOD",
            is_news_blackout=False,
            signal_score=6.8,
            confidence=0.68,
            risk_reward=2.0,
            indicators={"rsi": 40.0},
            decision="GO",
            reasoning="Fast path loss",
            decision_maker=DecisionMaker.FAST_PATH,
            trade_id="fp_2",
            pnl=-50.0,
            holding_time_seconds=1800
        ),
        # LLM win
        TradeJournalEntry(
            entry_id="llm_win_1",
            timestamp=datetime.utcnow(),
            decision_type=DecisionType.TRADE_CLOSED,
            symbol="BTCUSD",
            direction="LONG",
            market_regime="VOLATILE",
            risk_appetite="AGGRESSIVE",
            liquidity_conditions="GOOD",
            is_news_blackout=False,
            signal_score=8.5,
            confidence=0.85,
            risk_reward=3.0,
            indicators={"rsi": 70.0},
            decision="GO",
            reasoning="LLM win",
            decision_maker=DecisionMaker.LLM,
            trade_id="llm_1",
            pnl=200.0,
            holding_time_seconds=7200
        )
    ]
    
    for entry in entries:
        journal.record_decision(entry)
    
    # Get performance breakdown
    perf = journal.get_performance_by_decision_maker()
    
    assert len(perf) == 2  # FAST_PATH and LLM
    
    # Check fast path stats
    fp_row = perf[perf['decision_maker'] == 'FAST_PATH'].iloc[0]
    assert fp_row['total_decisions'] == 2
    assert fp_row['wins'] == 1
    assert fp_row['losses'] == 1
    assert fp_row['win_rate'] == 0.5
    assert fp_row['total_pnl'] == 50.0
    
    # Check LLM stats
    llm_row = perf[perf['decision_maker'] == 'LLM'].iloc[0]
    assert llm_row['total_decisions'] == 1
    assert llm_row['wins'] == 1
    assert llm_row['losses'] == 0
    assert llm_row['win_rate'] == 1.0
    assert llm_row['total_pnl'] == 200.0


def test_get_performance_by_symbol(journal):
    """Test performance breakdown by symbol"""
    entries = [
        TradeJournalEntry(
            entry_id=f"symbol_test_{i}",
            timestamp=datetime.utcnow(),
            decision_type=DecisionType.TRADE_CLOSED,
            symbol="XAUUSD" if i < 2 else "EURUSD",
            direction="LONG",
            market_regime="TRENDING",
            risk_appetite="MODERATE",
            liquidity_conditions="GOOD",
            is_news_blackout=False,
            signal_score=7.5,
            confidence=0.75,
            risk_reward=2.5,
            indicators={"rsi": 65.0},
            decision="GO",
            reasoning="Test",
            decision_maker=DecisionMaker.FAST_PATH,
            trade_id=f"trade_{i}",
            pnl=100.0 if i % 2 == 0 else -50.0,
            holding_time_seconds=3600
        )
        for i in range(4)
    ]
    
    for entry in entries:
        journal.record_decision(entry)
    
    perf = journal.get_performance_by_symbol()
    
    assert len(perf) == 2  # XAUUSD and EURUSD
    assert all(perf['total_trades'] == 2)


def test_get_performance_by_regime(journal):
    """Test performance breakdown by market regime"""
    entries = [
        TradeJournalEntry(
            entry_id=f"regime_test_{i}",
            timestamp=datetime.utcnow(),
            decision_type=DecisionType.TRADE_CLOSED,
            symbol="XAUUSD",
            direction="LONG",
            market_regime="TRENDING" if i < 2 else "RANGING",
            risk_appetite="MODERATE",
            liquidity_conditions="GOOD",
            is_news_blackout=False,
            signal_score=7.5,
            confidence=0.75,
            risk_reward=2.5,
            indicators={"rsi": 65.0},
            decision="GO",
            reasoning="Test",
            decision_maker=DecisionMaker.FAST_PATH,
            trade_id=f"trade_{i}",
            pnl=100.0 if i % 2 == 0 else -50.0,
            holding_time_seconds=3600
        )
        for i in range(4)
    ]
    
    for entry in entries:
        journal.record_decision(entry)
    
    perf = journal.get_performance_by_regime()
    
    assert len(perf) == 2  # TRENDING and RANGING
    assert all(perf['total_trades'] == 2)


def test_export_to_csv(journal, tmp_path):
    """Test exporting journal to CSV"""
    # Record some decisions
    entries = [
        TradeJournalEntry(
            entry_id=f"export_test_{i}",
            timestamp=datetime.utcnow(),
            decision_type=DecisionType.SIGNAL_GENERATED,
            symbol="XAUUSD",
            direction="LONG",
            market_regime="TRENDING",
            risk_appetite="MODERATE",
            liquidity_conditions="GOOD",
            is_news_blackout=False,
            signal_score=7.5,
            confidence=0.75,
            risk_reward=2.5,
            indicators={"rsi": 65.0},
            decision="GO",
            reasoning="Test",
            decision_maker=DecisionMaker.FAST_PATH
        )
        for i in range(5)
    ]
    
    for entry in entries:
        journal.record_decision(entry)
    
    # Export to CSV
    csv_path = tmp_path / "journal_export.csv"
    journal.export_to_csv(str(csv_path))
    
    assert csv_path.exists()
    
    # Verify content
    import pandas as pd
    df = pd.read_csv(csv_path)
    assert len(df) == 5


def test_export_to_json(journal, tmp_path):
    """Test exporting journal to JSON"""
    # Record some decisions
    entries = [
        TradeJournalEntry(
            entry_id=f"json_export_test_{i}",
            timestamp=datetime.utcnow(),
            decision_type=DecisionType.SIGNAL_GENERATED,
            symbol="EURUSD",
            direction="SHORT",
            market_regime="RANGING",
            risk_appetite="CONSERVATIVE",
            liquidity_conditions="GOOD",
            is_news_blackout=False,
            signal_score=6.8,
            confidence=0.68,
            risk_reward=2.0,
            indicators={"rsi": 40.0},
            decision="NOGO",
            reasoning="Test",
            decision_maker=DecisionMaker.LLM
        )
        for i in range(3)
    ]
    
    for entry in entries:
        journal.record_decision(entry)
    
    # Export to JSON
    json_path = tmp_path / "journal_export.json"
    journal.export_to_json(str(json_path))
    
    assert json_path.exists()
    
    # Verify content
    import json
    with open(json_path) as f:
        data = json.load(f)
    assert len(data) == 3


def test_record_decision_with_news_blackout(journal):
    """Test recording decision during news blackout"""
    entry = TradeJournalEntry(
        entry_id="blackout_test",
        timestamp=datetime.utcnow(),
        decision_type=DecisionType.SIGNAL_REJECTED,
        symbol="XAUUSD",
        direction="LONG",
        market_regime="VOLATILE",
        risk_appetite="CONSERVATIVE",
        liquidity_conditions="POOR",
        is_news_blackout=True,
        signal_score=7.5,
        confidence=0.75,
        risk_reward=2.5,
        indicators={"rsi": 65.0},
        decision="NOGO",
        reasoning="News blackout - high-impact event scheduled",
        decision_maker=DecisionMaker.SYSTEM
    )
    
    journal.record_decision(entry)
    
    retrieved = journal.get_decision_by_id("blackout_test")
    assert retrieved['is_news_blackout'] is True
    assert retrieved['decision'] == "NOGO"
    assert retrieved['decision_maker'] == "SYSTEM"


def test_empty_journal_queries(journal):
    """Test queries on empty journal"""
    # Should return empty DataFrames, not errors
    history = journal.get_decision_history()
    assert len(history) == 0
    
    perf_dm = journal.get_performance_by_decision_maker()
    assert len(perf_dm) == 0
    
    perf_symbol = journal.get_performance_by_symbol()
    assert len(perf_symbol) == 0
    
    perf_regime = journal.get_performance_by_regime()
    assert len(perf_regime) == 0

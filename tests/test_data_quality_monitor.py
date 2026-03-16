"""
Tests for DataQualityMonitor
Validates detection of missing data, price spikes, stuck prices, and timestamp anomalies.
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from data.data_quality_monitor import (
    DataQualityMonitor,
    DataIssue,
    IssueType,
    IssueSeverity,
)
from data.collectors.models import Tick
from data.event_bus import EventBus, Event, EventType


@pytest.fixture
async def event_bus():
    """Create event bus for testing"""
    bus = EventBus(max_queue_depth=100)
    await bus.start()
    yield bus
    await bus.stop()


@pytest.fixture
async def monitor(event_bus):
    """Create data quality monitor for testing"""
    symbols = ["EURUSD", "GBPUSD"]
    mon = DataQualityMonitor(
        event_bus=event_bus,
        symbols=symbols,
        check_interval_seconds=1,  # Fast checks for testing
        missing_data_threshold_seconds=60,
        price_spike_std_threshold=5.0,
        stuck_price_threshold_seconds=300,
        rolling_window_size=100,
    )
    await mon.start()
    yield mon
    await mon.stop()


class TestMissingDataDetection:
    """Test missing data gap detection"""
    
    @pytest.mark.asyncio
    async def test_detect_no_data_received(self, monitor):
        """Test detection when no data has been received"""
        issue = monitor.detect_missing_data("EURUSD")
        
        assert issue is not None
        assert issue.issue_type == IssueType.MISSING_DATA
        assert issue.severity == IssueSeverity.HIGH
        assert issue.symbol == "EURUSD"
        assert "No data received" in issue.description
        
    @pytest.mark.asyncio
    async def test_detect_missing_data_gap(self, monitor):
        """Test detection of data gap exceeding threshold"""
        # Simulate old tick
        old_time = datetime.utcnow() - timedelta(seconds=120)
        monitor._last_tick_time["EURUSD"] = old_time
        
        issue = monitor.detect_missing_data("EURUSD")
        
        assert issue is not None
        assert issue.issue_type == IssueType.MISSING_DATA
        assert issue.severity in [IssueSeverity.MEDIUM, IssueSeverity.HIGH]
        assert issue.details["gap_seconds"] >= 60
        
    @pytest.mark.asyncio
    async def test_no_issue_when_data_recent(self, monitor):
        """Test no issue when data is recent"""
        # Simulate recent tick
        monitor._last_tick_time["EURUSD"] = datetime.utcnow()
        
        issue = monitor.detect_missing_data("EURUSD")
        
        assert issue is None
        
    @pytest.mark.asyncio
    async def test_severity_scales_with_gap_size(self, monitor):
        """Test that severity increases with gap size"""
        # Small gap (2 minutes) - MEDIUM
        monitor._last_tick_time["EURUSD"] = datetime.utcnow() - timedelta(seconds=120)
        issue_medium = monitor.detect_missing_data("EURUSD")
        
        # Large gap (6 minutes) - CRITICAL
        monitor._last_tick_time["EURUSD"] = datetime.utcnow() - timedelta(seconds=360)
        issue_critical = monitor.detect_missing_data("EURUSD")
        
        assert issue_medium.severity == IssueSeverity.MEDIUM
        assert issue_critical.severity == IssueSeverity.CRITICAL


class TestPriceSpikeDetection:
    """Test price spike detection"""
    
    @pytest.mark.asyncio
    async def test_detect_price_spike(self, monitor):
        """Test detection of abnormal price spike"""
        # Add normal ticks
        base_price = 1.1000
        for i in range(50):
            tick = Tick(
                symbol="EURUSD",
                timestamp=datetime.utcnow(),
                bid=base_price - 0.0001,
                ask=base_price + 0.0001,
                last=base_price + (i * 0.00001),  # Small variations
                volume=100,
            )
            monitor._recent_ticks["EURUSD"].append(tick)
            
        # Update statistics
        monitor._update_statistics("EURUSD")
        
        # Add spike tick (10 std deviations away)
        spike_tick = Tick(
            symbol="EURUSD",
            timestamp=datetime.utcnow(),
            bid=base_price + 0.01 - 0.0001,
            ask=base_price + 0.01 + 0.0001,
            last=base_price + 0.01,  # Huge spike
            volume=100,
        )
        monitor._recent_ticks["EURUSD"].append(spike_tick)
        monitor._update_statistics("EURUSD")
        
        issue = monitor.detect_price_spikes("EURUSD")
        
        assert issue is not None
        assert issue.issue_type == IssueType.PRICE_SPIKE
        assert issue.details["z_score"] > 5.0
        assert issue.severity in [IssueSeverity.MEDIUM, IssueSeverity.HIGH, IssueSeverity.CRITICAL]
        
    @pytest.mark.asyncio
    async def test_no_spike_with_normal_prices(self, monitor):
        """Test no spike detected with normal price movements"""
        # Add normal ticks with small variations
        base_price = 1.1000
        for i in range(50):
            tick = Tick(
                symbol="EURUSD",
                timestamp=datetime.utcnow(),
                bid=base_price - 0.0001,
                ask=base_price + 0.0001,
                last=base_price + (i * 0.00001),
                volume=100,
            )
            monitor._recent_ticks["EURUSD"].append(tick)
            
        monitor._update_statistics("EURUSD")
        
        issue = monitor.detect_price_spikes("EURUSD")
        
        assert issue is None
        
    @pytest.mark.asyncio
    async def test_insufficient_data_no_spike_detection(self, monitor):
        """Test no spike detection with insufficient data"""
        # Add only a few ticks
        for i in range(5):
            tick = Tick(
                symbol="EURUSD",
                timestamp=datetime.utcnow(),
                bid=1.1000,
                ask=1.1002,
                last=1.1001,
                volume=100,
            )
            monitor._recent_ticks["EURUSD"].append(tick)
            
        issue = monitor.detect_price_spikes("EURUSD")
        
        assert issue is None


class TestStuckPriceDetection:
    """Test stuck price detection"""
    
    @pytest.mark.asyncio
    async def test_detect_stuck_price(self, monitor):
        """Test detection of stuck price"""
        # Simulate price that hasn't changed for 6 minutes
        old_time = datetime.utcnow() - timedelta(seconds=360)
        monitor._last_price_change_time["EURUSD"] = old_time
        monitor._last_price["EURUSD"] = 1.1000
        
        issue = monitor.detect_stuck_prices("EURUSD")
        
        assert issue is not None
        assert issue.issue_type == IssueType.STUCK_PRICE
        assert issue.details["stuck_seconds"] >= 300
        assert issue.severity in [IssueSeverity.MEDIUM, IssueSeverity.HIGH]
        
    @pytest.mark.asyncio
    async def test_no_issue_when_price_changes(self, monitor):
        """Test no issue when price changes regularly"""
        # Simulate recent price change
        monitor._last_price_change_time["EURUSD"] = datetime.utcnow()
        monitor._last_price["EURUSD"] = 1.1000
        
        issue = monitor.detect_stuck_prices("EURUSD")
        
        assert issue is None
        
    @pytest.mark.asyncio
    async def test_severity_scales_with_stuck_duration(self, monitor):
        """Test that severity increases with stuck duration"""
        # Medium stuck (6 minutes)
        monitor._last_price_change_time["EURUSD"] = datetime.utcnow() - timedelta(seconds=360)
        issue_medium = monitor.detect_stuck_prices("EURUSD")
        
        # Critical stuck (16 minutes)
        monitor._last_price_change_time["EURUSD"] = datetime.utcnow() - timedelta(seconds=960)
        issue_critical = monitor.detect_stuck_prices("EURUSD")
        
        assert issue_medium.severity == IssueSeverity.MEDIUM
        assert issue_critical.severity == IssueSeverity.CRITICAL


class TestTimestampAnomalyDetection:
    """Test timestamp anomaly detection"""
    
    @pytest.mark.asyncio
    async def test_detect_out_of_order_timestamps(self, monitor):
        """Test detection of out-of-order timestamps"""
        # Add ticks with out-of-order timestamps
        now = datetime.utcnow()
        
        tick1 = Tick(
            symbol="EURUSD",
            timestamp=now,
            bid=1.1000,
            ask=1.1002,
            last=1.1001,
            volume=100,
        )
        tick2 = Tick(
            symbol="EURUSD",
            timestamp=now - timedelta(seconds=10),  # Earlier than tick1
            bid=1.1000,
            ask=1.1002,
            last=1.1001,
            volume=100,
        )
        
        monitor._recent_ticks["EURUSD"].append(tick1)
        monitor._recent_ticks["EURUSD"].append(tick2)
        
        issues = monitor.detect_timestamp_anomalies("EURUSD")
        
        assert len(issues) > 0
        assert any(issue.issue_type == IssueType.TIMESTAMP_ANOMALY for issue in issues)
        assert any("Out-of-order" in issue.description for issue in issues)
        
    @pytest.mark.asyncio
    async def test_detect_future_timestamps(self, monitor):
        """Test detection of future timestamps"""
        # Add a normal tick first (required for the check to work)
        normal_tick = Tick(
            symbol="EURUSD",
            timestamp=datetime.utcnow() - timedelta(seconds=10),
            bid=1.1000,
            ask=1.1002,
            last=1.1001,
            volume=100,
        )
        monitor._recent_ticks["EURUSD"].append(normal_tick)
        
        # Add tick with future timestamp (>5 seconds ahead to exceed threshold)
        future_time = datetime.utcnow() + timedelta(seconds=30)
        
        tick = Tick(
            symbol="EURUSD",
            timestamp=future_time,
            bid=1.1000,
            ask=1.1002,
            last=1.1001,
            volume=100,
        )
        
        monitor._recent_ticks["EURUSD"].append(tick)
        
        issues = monitor.detect_timestamp_anomalies("EURUSD")
        
        assert len(issues) > 0
        assert any(issue.issue_type == IssueType.TIMESTAMP_ANOMALY for issue in issues)
        assert any("Future timestamp" in issue.description for issue in issues)
        
    @pytest.mark.asyncio
    async def test_no_anomaly_with_correct_timestamps(self, monitor):
        """Test no anomaly with correctly ordered timestamps"""
        # Add ticks with correct timestamps
        base_time = datetime.utcnow() - timedelta(seconds=60)
        
        for i in range(10):
            tick = Tick(
                symbol="EURUSD",
                timestamp=base_time + timedelta(seconds=i),
                bid=1.1000,
                ask=1.1002,
                last=1.1001,
                volume=100,
            )
            monitor._recent_ticks["EURUSD"].append(tick)
            
        issues = monitor.detect_timestamp_anomalies("EURUSD")
        
        assert len(issues) == 0


class TestEventIntegration:
    """Test integration with event bus"""
    
    @pytest.mark.asyncio
    async def test_processes_market_data_events(self, monitor, event_bus):
        """Test that monitor processes market data events"""
        # Publish market data event
        tick_data = {
            "time": datetime.utcnow(),
            "bid": 1.1000,
            "ask": 1.1002,
            "last": 1.1001,
            "volume": 100,
            "spread": 0.0002,
            "spread_pct": 0.018,
            "tick_direction": 1,
        }
        
        event = Event(
            type=EventType.MARKET_DATA_UPDATED,
            timestamp=datetime.utcnow(),
            data={
                "symbol": "EURUSD",
                "tick": tick_data,
            },
            source="test"
        )
        
        await event_bus.publish(event)
        await asyncio.sleep(0.1)  # Allow processing
        
        # Check that tick was added to buffer
        assert len(monitor._recent_ticks["EURUSD"]) > 0
        assert "EURUSD" in monitor._last_tick_time
        
    @pytest.mark.asyncio
    async def test_emits_data_quality_alerts(self, monitor, event_bus):
        """Test that monitor emits data quality alert events"""
        # Set up alert capture
        alerts_received = []
        
        async def capture_alert(event: Event):
            if event.type == EventType.DATA_QUALITY_ALERT:
                alerts_received.append(event)
                
        await event_bus.subscribe(EventType.DATA_QUALITY_ALERT, capture_alert)
        
        # Create a data quality issue
        monitor._last_tick_time["EURUSD"] = datetime.utcnow() - timedelta(seconds=120)
        
        # Run check
        await monitor.check_all_symbols()
        await asyncio.sleep(0.2)  # Allow event processing
        
        # Verify alert was emitted
        assert len(alerts_received) > 0
        alert_event = alerts_received[0]
        assert alert_event.type == EventType.DATA_QUALITY_ALERT
        assert "issue" in alert_event.data


class TestMonitoringLoop:
    """Test monitoring loop functionality"""
    
    @pytest.mark.asyncio
    async def test_monitoring_loop_runs_periodically(self, monitor):
        """Test that monitoring loop runs checks periodically"""
        # Set up a detectable issue
        monitor._last_tick_time["EURUSD"] = datetime.utcnow() - timedelta(seconds=120)
        
        initial_issues = monitor._total_issues_detected
        
        # Wait for at least one check cycle
        await asyncio.sleep(1.5)
        
        # Verify checks ran
        assert monitor._total_issues_detected > initial_issues
        
    @pytest.mark.asyncio
    async def test_active_issues_tracking(self, monitor):
        """Test tracking of active issues"""
        # Create issue
        monitor._last_tick_time["EURUSD"] = datetime.utcnow() - timedelta(seconds=120)
        
        # Run check
        await monitor.check_all_symbols()
        
        # Verify active issues
        active_issues = monitor.get_active_issues("EURUSD")
        assert len(active_issues) > 0
        
        # Clear issue
        monitor._last_tick_time["EURUSD"] = datetime.utcnow()
        
        # Run check again
        await monitor.check_all_symbols()
        
        # Verify issues cleared
        active_issues = monitor.get_active_issues("EURUSD")
        assert len(active_issues) == 0


class TestMetrics:
    """Test metrics collection"""
    
    @pytest.mark.asyncio
    async def test_get_metrics(self, monitor):
        """Test metrics retrieval"""
        metrics = monitor.get_metrics()
        
        assert "running" in metrics
        assert "symbols_monitored" in metrics
        assert "total_issues_detected" in metrics
        assert "active_issues" in metrics
        assert "check_interval_seconds" in metrics
        assert "uptime_seconds" in metrics
        
        assert metrics["running"] is True
        assert metrics["symbols_monitored"] == 2
        assert metrics["check_interval_seconds"] == 1
        
    @pytest.mark.asyncio
    async def test_metrics_track_issues(self, monitor):
        """Test that metrics track detected issues"""
        initial_total = monitor._total_issues_detected
        
        # Create issue
        monitor._last_tick_time["EURUSD"] = datetime.utcnow() - timedelta(seconds=120)
        await monitor.check_all_symbols()
        
        metrics = monitor.get_metrics()
        
        assert metrics["total_issues_detected"] > initial_total
        assert metrics["active_issues"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

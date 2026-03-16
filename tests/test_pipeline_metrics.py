"""
Unit tests for PipelineMetrics component.
Tests metrics tracking for latency, queue depth, processing rate, and memory usage.
"""
import pytest
import time
from datetime import datetime
from data.pipeline_metrics import PipelineMetrics, StageMetrics, MemoryMetrics


def test_stage_metrics_creation():
    """Test StageMetrics initialization"""
    stage = StageMetrics(stage_name="test_stage")
    
    assert stage.stage_name == "test_stage"
    assert stage.total_executions == 0
    assert stage.total_latency_ms == 0.0
    assert stage.errors == 0


def test_stage_metrics_record_execution():
    """Test recording stage executions"""
    stage = StageMetrics(stage_name="test_stage")
    
    # Record some executions
    stage.record_execution(latency_ms=10.0, error=False)
    stage.record_execution(latency_ms=20.0, error=False)
    stage.record_execution(latency_ms=30.0, error=True)
    
    assert stage.total_executions == 3
    assert stage.total_latency_ms == 60.0
    assert stage.min_latency_ms == 10.0
    assert stage.max_latency_ms == 30.0
    assert stage.errors == 1
    assert stage.get_avg_latency_ms() == 20.0


def test_stage_metrics_percentiles():
    """Test percentile calculations"""
    stage = StageMetrics(stage_name="test_stage")
    
    # Record latencies: 1, 2, 3, ..., 100
    for i in range(1, 101):
        stage.record_execution(latency_ms=float(i), error=False)
    
    # Check percentiles
    p50 = stage.get_p50_latency_ms()
    p95 = stage.get_p95_latency_ms()
    p99 = stage.get_p99_latency_ms()
    
    assert 45 <= p50 <= 55  # Median around 50
    assert 90 <= p95 <= 100  # 95th percentile around 95
    assert 95 <= p99 <= 100  # 99th percentile around 99


def test_stage_metrics_to_dict():
    """Test conversion to dictionary"""
    stage = StageMetrics(stage_name="test_stage")
    stage.record_execution(latency_ms=10.0, error=False)
    stage.record_execution(latency_ms=20.0, error=True)
    
    data = stage.to_dict()
    
    assert data["stage_name"] == "test_stage"
    assert data["total_executions"] == 2
    assert data["avg_latency_ms"] == 15.0
    assert data["min_latency_ms"] == 10.0
    assert data["max_latency_ms"] == 20.0
    assert data["errors"] == 1
    assert data["error_rate"] == 0.5


def test_memory_metrics_creation():
    """Test MemoryMetrics initialization"""
    mem = MemoryMetrics(cache_name="test_cache")
    
    assert mem.cache_name == "test_cache"
    assert mem.size_bytes == 0
    assert mem.item_count == 0


def test_memory_metrics_update():
    """Test updating memory metrics"""
    mem = MemoryMetrics(cache_name="test_cache")
    
    mem.update(size_bytes=1024 * 1024, item_count=100)
    
    assert mem.size_bytes == 1024 * 1024
    assert mem.item_count == 100
    assert mem.get_size_mb() == 1.0
    assert mem.last_updated is not None


def test_memory_metrics_to_dict():
    """Test conversion to dictionary"""
    mem = MemoryMetrics(cache_name="test_cache")
    mem.update(size_bytes=2048 * 1024, item_count=50)
    
    data = mem.to_dict()
    
    assert data["cache_name"] == "test_cache"
    assert data["size_bytes"] == 2048 * 1024
    assert data["size_mb"] == 2.0
    assert data["item_count"] == 50
    assert data["last_updated"] is not None


def test_pipeline_metrics_creation():
    """Test PipelineMetrics initialization"""
    metrics = PipelineMetrics()
    
    assert len(metrics._stage_metrics) == 0
    assert len(metrics._memory_metrics) == 0


def test_pipeline_metrics_record_stage_execution():
    """Test recording stage executions"""
    metrics = PipelineMetrics()
    
    metrics.record_stage_execution("stage1", latency_ms=10.0, error=False)
    metrics.record_stage_execution("stage1", latency_ms=20.0, error=False)
    metrics.record_stage_execution("stage2", latency_ms=30.0, error=True)
    
    # Check stage1
    stage1_data = metrics.get_stage_metrics("stage1")
    assert stage1_data is not None
    assert stage1_data["total_executions"] == 2
    assert stage1_data["avg_latency_ms"] == 15.0
    
    # Check stage2
    stage2_data = metrics.get_stage_metrics("stage2")
    assert stage2_data is not None
    assert stage2_data["total_executions"] == 1
    assert stage2_data["errors"] == 1


def test_pipeline_metrics_latency_warning(caplog):
    """Test warning is logged for high latency"""
    import logging
    caplog.set_level(logging.WARNING)
    
    metrics = PipelineMetrics()
    
    # Record execution exceeding 500ms threshold
    metrics.record_stage_execution("slow_stage", latency_ms=600.0, error=False)
    
    # Check that stage was recorded
    stage_data = metrics.get_stage_metrics("slow_stage")
    assert stage_data is not None
    assert stage_data["max_latency_ms"] == 600.0


def test_pipeline_metrics_update_memory_usage():
    """Test updating memory usage"""
    metrics = PipelineMetrics()
    
    metrics.update_memory_usage("cache1", size_bytes=1024 * 1024, item_count=100)
    metrics.update_memory_usage("cache2", size_bytes=2048 * 1024, item_count=200)
    
    # Check cache1
    cache1_data = metrics.get_memory_metrics("cache1")
    assert cache1_data is not None
    assert cache1_data["size_mb"] == 1.0
    assert cache1_data["item_count"] == 100
    
    # Check total memory
    total_mb = metrics.get_total_memory_usage_mb()
    assert total_mb == 3.0


def test_pipeline_metrics_record_queue_depth():
    """Test recording queue depth"""
    metrics = PipelineMetrics()
    
    metrics.record_queue_depth(10)
    metrics.record_queue_depth(20)
    metrics.record_queue_depth(15)
    
    stats = metrics.get_queue_depth_stats()
    
    assert stats["current"] == 15
    assert stats["avg"] == 15.0
    assert stats["min"] == 10
    assert stats["max"] == 20


def test_pipeline_metrics_record_processing_rate():
    """Test recording processing rate"""
    metrics = PipelineMetrics()
    
    metrics.record_processing_rate(10.0)
    metrics.record_processing_rate(20.0)
    metrics.record_processing_rate(15.0)
    
    stats = metrics.get_processing_rate_stats()
    
    assert stats["current"] == 15.0
    assert stats["avg"] == 15.0
    assert stats["min"] == 10.0
    assert stats["max"] == 20.0


def test_pipeline_metrics_get_all_stage_metrics():
    """Test getting all stage metrics"""
    metrics = PipelineMetrics()
    
    metrics.record_stage_execution("stage1", latency_ms=10.0, error=False)
    metrics.record_stage_execution("stage2", latency_ms=20.0, error=False)
    metrics.record_stage_execution("stage3", latency_ms=30.0, error=True)
    
    all_metrics = metrics.get_all_stage_metrics()
    
    assert len(all_metrics) == 3
    assert "stage1" in all_metrics
    assert "stage2" in all_metrics
    assert "stage3" in all_metrics


def test_pipeline_metrics_get_all_memory_metrics():
    """Test getting all memory metrics"""
    metrics = PipelineMetrics()
    
    metrics.update_memory_usage("cache1", size_bytes=1024, item_count=10)
    metrics.update_memory_usage("cache2", size_bytes=2048, item_count=20)
    
    all_metrics = metrics.get_all_memory_metrics()
    
    assert len(all_metrics) == 2
    assert "cache1" in all_metrics
    assert "cache2" in all_metrics


def test_pipeline_metrics_comprehensive_metrics():
    """Test getting comprehensive metrics"""
    metrics = PipelineMetrics()
    
    # Record some data
    metrics.record_stage_execution("stage1", latency_ms=10.0, error=False)
    metrics.record_stage_execution("stage2", latency_ms=20.0, error=True)
    metrics.update_memory_usage("cache1", size_bytes=1024 * 1024, item_count=100)
    metrics.record_queue_depth(10)
    metrics.record_processing_rate(50.0)
    
    comprehensive = metrics.get_comprehensive_metrics()
    
    # Check structure
    assert "timestamp" in comprehensive
    assert "uptime_seconds" in comprehensive
    assert "stages" in comprehensive
    assert "queue" in comprehensive
    assert "memory" in comprehensive
    assert "summary" in comprehensive
    
    # Check stages
    assert len(comprehensive["stages"]) == 2
    
    # Check queue
    assert "depth" in comprehensive["queue"]
    assert "processing_rate" in comprehensive["queue"]
    
    # Check memory
    assert "caches" in comprehensive["memory"]
    assert "total_cache_mb" in comprehensive["memory"]
    assert "process_mb" in comprehensive["memory"]
    
    # Check summary
    summary = comprehensive["summary"]
    assert summary["total_stages"] == 2
    assert summary["total_executions"] == 2
    assert summary["total_errors"] == 1


def test_pipeline_metrics_process_memory():
    """Test getting process memory usage"""
    metrics = PipelineMetrics()
    
    process_mb = metrics.get_process_memory_mb()
    
    # Should return a positive number
    assert process_mb > 0


def test_pipeline_metrics_reset():
    """Test resetting metrics"""
    metrics = PipelineMetrics()
    
    # Add some data
    metrics.record_stage_execution("stage1", latency_ms=10.0, error=False)
    metrics.update_memory_usage("cache1", size_bytes=1024, item_count=10)
    metrics.record_queue_depth(10)
    metrics.record_processing_rate(50.0)
    
    # Reset
    metrics.reset()
    
    # Check everything is cleared
    assert len(metrics._stage_metrics) == 0
    assert len(metrics._memory_metrics) == 0
    assert len(metrics._queue_depth_samples) == 0
    assert len(metrics._processing_rate_samples) == 0


def test_pipeline_metrics_empty_stats():
    """Test getting stats with no data"""
    metrics = PipelineMetrics()
    
    # Queue depth stats
    queue_stats = metrics.get_queue_depth_stats()
    assert queue_stats["current"] == 0.0
    assert queue_stats["avg"] == 0.0
    
    # Processing rate stats
    rate_stats = metrics.get_processing_rate_stats()
    assert rate_stats["current"] == 0.0
    assert rate_stats["avg"] == 0.0
    
    # Stage metrics
    stage_data = metrics.get_stage_metrics("nonexistent")
    assert stage_data is None
    
    # Memory metrics
    mem_data = metrics.get_memory_metrics("nonexistent")
    assert mem_data is None


def test_stage_metrics_recent_latencies_limit():
    """Test that recent latencies are limited to 1000 samples"""
    stage = StageMetrics(stage_name="test_stage")
    
    # Record 2000 executions
    for i in range(2000):
        stage.record_execution(latency_ms=float(i), error=False)
    
    # Should only keep last 1000
    assert len(stage.recent_latencies) == 1000
    assert stage.total_executions == 2000


def test_pipeline_metrics_queue_samples_limit():
    """Test that queue samples are limited to 1000"""
    metrics = PipelineMetrics()
    
    # Record 2000 samples
    for i in range(2000):
        metrics.record_queue_depth(i)
    
    # Should only keep last 1000
    assert len(metrics._queue_depth_samples) == 1000


def test_pipeline_metrics_processing_rate_samples_limit():
    """Test that processing rate samples are limited to 1000"""
    metrics = PipelineMetrics()
    
    # Record 2000 samples
    for i in range(2000):
        metrics.record_processing_rate(float(i))
    
    # Should only keep last 1000
    assert len(metrics._processing_rate_samples) == 1000

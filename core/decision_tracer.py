"""
APEX Bot — Decision Tracer
Captures complete decision-making process with agent-level logs and reasoning.
"""
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
import json

from core.logger import get_agent_logger

log = get_agent_logger("DECISION_TRACER")


class DecisionType(str, Enum):
    TRADE_OPENED = "TRADE_OPENED"
    TRADE_REJECTED = "TRADE_REJECTED"
    TRADE_CLOSED = "TRADE_CLOSED"
    POSITION_ADJUSTED = "POSITION_ADJUSTED"


class StepStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class AgentLog:
    """Individual log entry from an agent"""
    agent_name: str
    timestamp: str
    log_level: str
    message: str
    context: Optional[Dict[str, Any]] = None


@dataclass
class DecisionStep:
    """Single step in the decision-making process"""
    step_number: int
    step_name: str
    agent: str
    timestamp: str
    duration_ms: int
    status: StepStatus
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    reasoning: Optional[str] = None
    agent_logs: List[AgentLog] = field(default_factory=list)


@dataclass
class DecisionTrace:
    """Complete trace of a trading decision"""
    decision_id: str
    timestamp: str
    symbol: str
    decision_type: DecisionType
    final_decision: str
    confidence: float
    total_duration_ms: int
    steps: List[DecisionStep]
    market_state: Dict[str, Any]
    rejection_reason: Optional[str] = None


class DecisionTracer:
    """
    Captures and stores complete decision traces with agent logs.
    
    Usage:
        tracer = DecisionTracer(symbol="XAUUSD")
        
        with tracer.step("Signal Generation", "FastDecisionEngine") as step:
            step.log("INFO", "Calculating signal score")
            step.set_input({"price": 2050.0, "indicators": {...}})
            signal_score = calculate_signal()
            step.set_output({"signal_score": signal_score})
            step.set_reasoning("Signal score above threshold")
            
            if signal_score < threshold:
                step.fail()
        
        tracer.finalize(
            decision_type=DecisionType.TRADE_OPENED,
            final_decision="LONG 0.5 lots",
            confidence=85.0
        )
    """
    
    def __init__(self, symbol: str, market_state: Optional[Dict[str, Any]] = None):
        self.decision_id = str(uuid.uuid4())
        self.symbol = symbol
        self.start_time = time.time()
        self.timestamp = datetime.utcnow().isoformat()
        self.market_state = market_state or {}
        self.steps: List[DecisionStep] = []
        self.current_step_number = 0
        self._finalized = False
    
    def step(self, step_name: str, agent: str):
        """
        Context manager for a decision step.
        
        Args:
            step_name: Name of the decision step
            agent: Name of the agent executing this step
        
        Returns:
            StepContext: Context manager for the step
        """
        self.current_step_number += 1
        return StepContext(self, step_name, agent, self.current_step_number)
    
    def add_step(self, step: DecisionStep):
        """Add a completed step to the trace"""
        self.steps.append(step)
    
    def finalize(
        self,
        decision_type: DecisionType,
        final_decision: str,
        confidence: float,
        rejection_reason: Optional[str] = None
    ) -> DecisionTrace:
        """
        Finalize the decision trace and store it.
        
        Args:
            decision_type: Type of decision made
            final_decision: Human-readable final decision
            confidence: Confidence level (0-100)
            rejection_reason: Reason if trade was rejected
        
        Returns:
            DecisionTrace: Complete decision trace
        """
        if self._finalized:
            log.warning(f"Decision {self.decision_id} already finalized")
            return self._get_trace(decision_type, final_decision, confidence, rejection_reason)
        
        self._finalized = True
        total_duration_ms = int((time.time() - self.start_time) * 1000)
        
        trace = DecisionTrace(
            decision_id=self.decision_id,
            timestamp=self.timestamp,
            symbol=self.symbol,
            decision_type=decision_type,
            final_decision=final_decision,
            confidence=confidence,
            total_duration_ms=total_duration_ms,
            steps=self.steps,
            market_state=self.market_state,
            rejection_reason=rejection_reason
        )
        
        # Store trace (in production, save to database)
        self._store_trace(trace)
        
        log.info(
            f"Decision trace finalized: {self.decision_id} | "
            f"{decision_type.value} | {self.symbol} | "
            f"{len(self.steps)} steps | {total_duration_ms}ms"
        )
        
        return trace
    
    def _get_trace(
        self,
        decision_type: DecisionType,
        final_decision: str,
        confidence: float,
        rejection_reason: Optional[str]
    ) -> DecisionTrace:
        """Get current trace state"""
        total_duration_ms = int((time.time() - self.start_time) * 1000)
        return DecisionTrace(
            decision_id=self.decision_id,
            timestamp=self.timestamp,
            symbol=self.symbol,
            decision_type=decision_type,
            final_decision=final_decision,
            confidence=confidence,
            total_duration_ms=total_duration_ms,
            steps=self.steps,
            market_state=self.market_state,
            rejection_reason=rejection_reason
        )
    
    def _store_trace(self, trace: DecisionTrace):
        """Store trace to database (implement in production)"""
        # In production, store to DuckDB or TimescaleDB
        # For now, just log
        log.debug(f"Storing trace: {trace.decision_id}")
        
        # Store in global registry for dashboard access
        _trace_registry[trace.decision_id] = trace


class StepContext:
    """Context manager for a decision step"""
    
    def __init__(self, tracer: DecisionTracer, step_name: str, agent: str, step_number: int):
        self.tracer = tracer
        self.step_name = step_name
        self.agent = agent
        self.step_number = step_number
        self.start_time = time.time()
        self.timestamp = datetime.utcnow().isoformat()
        self.status = StepStatus.PASSED
        self.input_data: Optional[Dict[str, Any]] = None
        self.output_data: Optional[Dict[str, Any]] = None
        self.reasoning: Optional[str] = None
        self.agent_logs: List[AgentLog] = []
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # If exception occurred, mark as failed
        if exc_type is not None:
            self.status = StepStatus.FAILED
            self.log("ERROR", f"Step failed with exception: {exc_val}")
        
        duration_ms = int((time.time() - self.start_time) * 1000)
        
        step = DecisionStep(
            step_number=self.step_number,
            step_name=self.step_name,
            agent=self.agent,
            timestamp=self.timestamp,
            duration_ms=duration_ms,
            status=self.status,
            input_data=self.input_data,
            output_data=self.output_data,
            reasoning=self.reasoning,
            agent_logs=self.agent_logs
        )
        
        self.tracer.add_step(step)
        
        # Don't suppress exceptions
        return False
    
    def log(self, level: str, message: str, context: Optional[Dict[str, Any]] = None):
        """Add a log entry for this step"""
        agent_log = AgentLog(
            agent_name=self.agent,
            timestamp=datetime.utcnow().isoformat(),
            log_level=level,
            message=message,
            context=context
        )
        self.agent_logs.append(agent_log)
    
    def set_input(self, data: Dict[str, Any]):
        """Set input data for this step"""
        self.input_data = data
    
    def set_output(self, data: Dict[str, Any]):
        """Set output data for this step"""
        self.output_data = data
    
    def set_reasoning(self, reasoning: str):
        """Set reasoning for this step"""
        self.reasoning = reasoning
    
    def fail(self, reason: Optional[str] = None):
        """Mark this step as failed"""
        self.status = StepStatus.FAILED
        if reason:
            self.log("ERROR", f"Step failed: {reason}")
    
    def skip(self, reason: Optional[str] = None):
        """Mark this step as skipped"""
        self.status = StepStatus.SKIPPED
        if reason:
            self.log("INFO", f"Step skipped: {reason}")


# Global trace registry (in production, use database)
_trace_registry: Dict[str, DecisionTrace] = {}


def get_trace(decision_id: str) -> Optional[DecisionTrace]:
    """Get a decision trace by ID"""
    return _trace_registry.get(decision_id)


def get_recent_traces(
    limit: int = 50,
    decision_type: Optional[DecisionType] = None,
    symbol: Optional[str] = None
) -> List[DecisionTrace]:
    """Get recent decision traces with optional filters"""
    traces = list(_trace_registry.values())
    
    # Sort by timestamp (most recent first)
    traces.sort(key=lambda t: t.timestamp, reverse=True)
    
    # Apply filters
    if decision_type:
        traces = [t for t in traces if t.decision_type == decision_type]
    if symbol:
        traces = [t for t in traces if t.symbol == symbol]
    
    return traces[:limit]


def clear_old_traces(keep_last_n: int = 1000):
    """Clear old traces to prevent memory bloat"""
    global _trace_registry
    
    if len(_trace_registry) <= keep_last_n:
        return
    
    traces = list(_trace_registry.values())
    traces.sort(key=lambda t: t.timestamp, reverse=True)
    
    # Keep only the most recent traces
    keep_ids = {t.decision_id for t in traces[:keep_last_n]}
    _trace_registry = {k: v for k, v in _trace_registry.items() if k in keep_ids}
    
    log.info(f"Cleared old traces, kept {len(_trace_registry)} most recent")

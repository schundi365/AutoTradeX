"""
APEX Bot — Autonomous Orchestrator with Fast Path
Hybrid decision engine: 90% rule-based, 10% LLM review.
"""
from __future__ import annotations
import asyncio
import json
import time
from datetime import datetime
from typing import List, Tuple

from loguru import logger as log

from core.models import BotState, TradingSignal, Trade
from core.config import settings
from core.fast_decision import FastDecisionEngine, Decision, analyze_cross_asset_signals
from core.market_context import MarketStateEngine, MarketContext
from core.data_lake import MarketDataLake
from core.outcome_tracker import OutcomeTracker, AdaptiveThresholds, Outcome
from llm.client import call_llm


class AutonomousOrchestrator:
    """
    Autonomous decision engine with fast path and adaptive learning.
    """
    
    def __init__(self):
        self.fast_engine = FastDecisionEngine()
        self.market_state = MarketStateEngine()
        self.data_lake = MarketDataLake()
        self.outcome_tracker = OutcomeTracker()
        self.adaptive_thresholds = AdaptiveThresholds(self.outcome_tracker)
        
        # Performance metrics
        self.total_decisions = 0
        self.fast_path_decisions = 0
        self.llm_decisions = 0
        self.avg_decision_time_ms = 0.0
    
    async def process_signals(self, state: BotState) -> BotState:
        """
        Main entry point: process all signals with fast path + LLM review.
        """
        start_time = time.time()
        
        if not state.approved_signals:
            log.info("[AUTONOMOUS] No approved signals to evaluate")
            return state
        
        log.info(f"[AUTONOMOUS] Processing {len(state.approved_signals)} signals...")
        
        # Update market state
        await self._update_market_state(state)
        
        # Get market context
        market_context = self.market_state.get_market_context(state.is_news_blackout)
        log.info(f"[AUTONOMOUS] Market context: {market_context.summary()}")
        
        # Apply cross-asset analysis for diversification
        diversified_signals = analyze_cross_asset_signals(
            state.approved_signals,
            self.market_state,
            max_per_cluster=2
        )
        
        log.info(
            f"[AUTONOMOUS] Diversification: {len(state.approved_signals)} → "
            f"{len(diversified_signals)} signals after correlation filtering"
        )
        
        # Fast path evaluation
        fast_approved, edge_cases = await self._fast_path_evaluation(
            diversified_signals,
            market_context
        )
        
        # Batch LLM review for edge cases
        llm_approved = []
        if edge_cases:
            llm_approved = await self._batch_llm_review(edge_cases, state, market_context)
        
        # Combine results
        final_approved = fast_approved + llm_approved
        
        # Performance metrics
        elapsed_ms = (time.time() - start_time) * 1000
        
        # Log decisions with timing
        await self._log_decisions(
            state.approved_signals, 
            final_approved, 
            market_context,
            decision_time_ms=int(elapsed_ms)
        )
        
        # Update state
        state.approved_signals = final_approved
        self.avg_decision_time_ms = (
            self.avg_decision_time_ms * 0.9 + elapsed_ms * 0.1
        )
        
        log.info(
            f"[AUTONOMOUS] Completed in {elapsed_ms:.0f}ms | "
            f"Fast path: {len(fast_approved)}, LLM: {len(llm_approved)} | "
            f"Total approved: {len(final_approved)}/{len(state.approved_signals)}"
        )
        
        # Periodic adaptive threshold adjustment
        if self.total_decisions % 20 == 0 and self.total_decisions > 0:
            await self.adaptive_thresholds.adjust_based_on_performance()
        
        return state
    
    async def _update_market_state(self, state: BotState):
        """Update market state engine with latest data"""
        await self.market_state.update(
            quotes=state.quotes,
            ohlcv_cache=state.ohlcv_cache,
            macro_data=state.macro_data
        )
        
        # Update data lake
        await self.data_lake.update_all(
            quotes=state.quotes,
            ohlcv_data=state.ohlcv_cache,
            news=state.news_items,
            calendar=state.calendar_events
        )
    
    async def _fast_path_evaluation(
        self,
        signals: List[TradingSignal],
        market_context: MarketContext
    ) -> Tuple[List[TradingSignal], List[TradingSignal]]:
        """
        Evaluate signals using fast path rules.
        Returns: (approved_signals, edge_cases_needing_llm)
        """
        fast_approved = []
        edge_cases = []
        
        # Apply adaptive thresholds to fast engine
        thresholds = self.adaptive_thresholds.get_thresholds()
        self.fast_engine.weak_signal_score = thresholds["min_score"]
        self.fast_engine.weak_confidence = thresholds["min_confidence"]
        self.fast_engine.weak_risk_reward = thresholds["min_rr"]
        
        for signal in signals:
            result = await self.fast_engine.evaluate(signal, market_context)
            
            if result.decision == Decision.GO:
                fast_approved.append(signal)
                self.fast_path_decisions += 1
                log.info(
                    f"[FAST_PATH] ✓ {signal.symbol} {signal.direction} — {result.reason}"
                )
            
            elif result.decision == Decision.NOGO:
                self.fast_path_decisions += 1
                log.info(
                    f"[FAST_PATH] ✗ {signal.symbol} {signal.direction} — {result.reason}"
                )
            
            else:  # NEEDS_REVIEW
                edge_cases.append(signal)
                log.info(
                    f"[FAST_PATH] ? {signal.symbol} {signal.direction} — needs LLM review"
                )
            
            self.total_decisions += 1
        
        fast_path_pct = (self.fast_path_decisions / max(self.total_decisions, 1)) * 100
        log.info(
            f"[FAST_PATH] Stats: {fast_path_pct:.1f}% fast path "
            f"({self.fast_path_decisions}/{self.total_decisions} decisions)"
        )
        
        return fast_approved, edge_cases
    
    async def _batch_llm_review(
        self,
        edge_cases: List[TradingSignal],
        state: BotState,
        market_context: MarketContext
    ) -> List[TradingSignal]:
        """
        Review multiple edge cases in one LLM call.
        """
        if not edge_cases:
            return []
        
        log.info(f"[LLM_BATCH] Reviewing {len(edge_cases)} edge cases...")
        
        start_time = time.time()
        
        # Prepare batch prompt
        signals_json = json.dumps([
            {
                "symbol": s.symbol,
                "direction": s.direction.value if hasattr(s.direction, "value") else s.direction,
                "score": s.score,
                "confidence": s.confidence,
                "risk_reward": s.risk_reward,
                "rsi": s.metadata.get("rsi", 50),
                "adx": s.metadata.get("adx", 20),
                "atr_pct": s.metadata.get("atr_pct", 0.0),
                "volume_ratio": s.metadata.get("volume_ratio", 1.0),
                "reasoning": s.reasoning[:150] if s.reasoning else ""
            }
            for s in edge_cases
        ], indent=2)
        
        system_prompt = """You are an expert trading decision maker reviewing edge cases.
These signals passed basic filters but need expert judgment.
Consider: signal quality, market context, risk/reward, and technical indicators.
Be selective - only approve high-conviction trades.
Return ONLY a JSON array: [{"symbol": "XAUUSD", "decision": "GO", "reason": "brief"}, ...]"""
        
        user_prompt = f"""Market Context:
{market_context.summary()}

Portfolio:
- Open trades: {len(state.open_trades)}
- Market regime: {state.market_regime}
- News blackout: {state.is_news_blackout}

Edge Case Signals:
{signals_json}

Review each signal and decide GO or NOGO. Return JSON array only."""
        
        try:
            response = await call_llm(
                system_prompt,
                user_prompt,
                max_tokens=1024,
                agent="autonomous_orchestrator"
            )
            
            # Handle None response (all LLM tiers failed)
            if response is None:
                log.error("[LLM_BATCH] All LLM tiers failed, using fallback logic")
                # Fallback: approve all signals (fast path already filtered them)
                approved = []
                for signal in edge_cases:
                    approved.append(signal)
                    log.info(
                        f"[LLM_BATCH] ✓ {signal.symbol} {signal.direction} — "
                        f"LLM unavailable, approved by fast path"
                    )
                self.llm_decisions += len(edge_cases)
                return approved
            
            # Parse response
            clean = response.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
                clean = clean.strip()
            
            decisions = json.loads(clean)
            
            if not isinstance(decisions, list):
                log.warning("[LLM_BATCH] Invalid response format, expected list")
                decisions = []
            
            # Map decisions back to signals
            decision_map = {
                d["symbol"]: d
                for d in decisions
                if isinstance(d, dict) and "symbol" in d
            }
            
            approved = []
            for signal in edge_cases:
                decision = decision_map.get(signal.symbol, {})
                if decision.get("decision") == "GO":
                    approved.append(signal)
                    log.info(
                        f"[LLM_BATCH] ✓ {signal.symbol} {signal.direction} — "
                        f"{decision.get('reason', 'approved')}"
                    )
                else:
                    log.info(
                        f"[LLM_BATCH] ✗ {signal.symbol} {signal.direction} — "
                        f"{decision.get('reason', 'rejected')}"
                    )
            
            self.llm_decisions += len(edge_cases)
            
            elapsed_ms = (time.time() - start_time) * 1000
            log.info(
                f"[LLM_BATCH] Reviewed {len(edge_cases)} signals in {elapsed_ms:.0f}ms "
                f"({elapsed_ms/len(edge_cases):.0f}ms per signal)"
            )
            
            return approved
            
        except Exception as e:
            log.error(f"[LLM_BATCH] Error: {e}")
            # Conservative fallback: reject all edge cases
            return []
    
    async def _log_decisions(
        self,
        all_signals: List[TradingSignal],
        approved_signals: List[TradingSignal],
        market_context: MarketContext,
        decision_time_ms: int = 0
    ):
        """Log all decisions for learning and to bot_decisions table"""
        from memory.duckdb_store import DuckDBStore
        from datetime import datetime, timezone
        
        approved_symbols = {s.symbol for s in approved_signals}
        
        # Log to DuckDB bot_decisions table for dashboard
        try:
            store = DuckDBStore(settings.training.duckdb_path)
            await store.start()
            await store.init_schema()
            
            for signal in all_signals:
                decision = "GO" if signal.symbol in approved_symbols else "NOGO"
                
                # Log to outcome tracker (for learning)
                await self.outcome_tracker.log_decision(signal, decision)
                
                # Log to bot_decisions table (for dashboard with timing)
                try:
                    await store.execute_write("""
                        INSERT INTO bot_decisions 
                        (timestamp, symbol, decision, confidence, outcome, decision_time_ms)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, [
                        datetime.now(timezone.utc),
                        signal.symbol,
                        decision,
                        signal.confidence,
                        None,  # Will be updated when trade closes
                        decision_time_ms
                    ])
                except Exception as e:
                    log.debug(f"Failed to log bot_decision for {signal.symbol}: {e}")
            
            await store.stop()
        except Exception as e:
            log.warning(f"Failed to log decisions to bot_decisions table: {e}")
    
    async def update_trade_outcome(self, trade: Trade):
        """Update outcome when trade closes"""
        if not trade.close_time:
            return
        
        pnl = getattr(trade, "pnl", 0.0)
        
        if pnl > 0:
            outcome = Outcome.WIN
        elif pnl < -10:  # Small threshold for breakeven
            outcome = Outcome.LOSS
        else:
            outcome = Outcome.BREAKEVEN
        
        await self.outcome_tracker.update_outcome(trade.id, outcome, pnl)
    
    def get_performance_stats(self) -> dict:
        """Get performance statistics"""
        recent_perf = self.outcome_tracker.get_recent_performance()
        regime_perf = self.outcome_tracker.get_regime_performance()
        thresholds = self.adaptive_thresholds.get_thresholds()
        
        return {
            "total_decisions": self.total_decisions,
            "fast_path_pct": (self.fast_path_decisions / max(self.total_decisions, 1)) * 100,
            "llm_decisions": self.llm_decisions,
            "avg_decision_time_ms": self.avg_decision_time_ms,
            "recent_performance": recent_perf,
            "regime_performance": regime_perf,
            "adaptive_thresholds": thresholds
        }

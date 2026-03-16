"""
APEX Bot — Agentic AI Framework (LangGraph)
Multi-agent graph: Orchestrator coordinates 5 specialist sub-agents.

Graph flow:
  START
    ↓
  [data_collector]       → fetches quotes, OHLCV, news, calendar
    ↓
  [macro_agent]          → DXY / yield macro context  (must run before strategy_adapter!)
    ↓
  [strategy_adapter]     → regime → adapted StrategyProfile + WatchdogReport
    ↓
  [market_analyst]       → technical analysis → raw signals (profile-adjusted)
    ↓
  [correlation_manager]  → correlation checks, divergence detection
    ↓
  [sentiment_agent]      → news/geo NLP → sentiment scores
    ↓
  [calendar_agent]       → check news blackouts, event risk
    ↓
  [risk_manager]         → filter/resize signals (uses regime-adapted gates)
    ↓
  [orchestrator]         → LLM final decision → approve/reject (watchdog context)
    ↓
  [execution_agent]      → place approved orders via broker
    ↓
  END
"""
from __future__ import annotations
import uuid
import asyncio
import json
from datetime import datetime, timedelta
from typing import Annotated, Literal

# LangGraph
try:
    from langgraph.graph import StateGraph, START, END
    from langgraph.graph.message import add_messages
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False

from core.models import (
    BotState, TradingSignal, SignalStrength, Direction,
    NewsImpact, AgentMessage, AssetClass, Trade, TradeStatus
)
from core.config import (
    settings,
    REGIME_SL_MULTIPLIERS, REGIME_TP_MULTIPLIERS,
    REGIME_RISK_MULTIPLIERS, CORRELATION_GROUPS,
)
from core.logger import get_agent_logger
from memory.duckdb_store import DuckDBStore
from llm.client import call_llm as llm_call  # Use centralized LLM client with rate limit handling
from agents.correlation_manager import (
    correlation_manager_node, build_correlation_summary,
)
from core.strategy_adaptation import get_engine as get_strategy_engine
from core.performance_watchdog import get_watchdog

log = get_agent_logger("AGENT")


# ═══════════════════════════════════════════════════════
#  LLM WRAPPER
# ═══════════════════════════════════════════════════════

async def call_llm(system: str, user: str, max_tokens: int = 1024, is_finetuned: bool = False, agent: str = "agent") -> str:
    """
    Wrapper for centralized LLM client with rate limit handling.
    The centralized client in llm.client handles Ollama → Groq → DeepSeek → Claude fallback.
    """
    result = await llm_call(system, user, max_tokens, agent)
    if result:
        return result
    # Fallback if all tiers fail
    return json.dumps({"error": "All LLM providers failed", "details": "No response from any tier"})


# ═══════════════════════════════════════════════════════
#  NODE: DATA COLLECTOR
# ═══════════════════════════════════════════════════════

async def data_collector_node(state: BotState) -> BotState:
    """
    Fetches: live quotes, recent OHLCV bars, latest news, calendar events.
    Populates state.quotes, state.ohlcv_cache, state.news_items, state.calendar_events.
    """
    log.info("[DATA] Refreshing market data for {} symbols...", len(settings.assets.all_symbols))

    # -- Import data modules lazily (avoids circular at import time)
    from data.market_feed import MarketFeed
    from data.news_feed import NewsFeed
    from data.calendar_feed import CalendarFeed

    feed    = MarketFeed()
    news    = NewsFeed()
    cal     = CalendarFeed()

    # Fetch in parallel
    quotes_task   = asyncio.gather(*[feed.get_quote(sym) for sym in settings.assets.all_symbols[:12]])
    news_task     = news.fetch_latest(limit=50)
    calendar_task = cal.fetch_upcoming(hours_ahead=48)

    quotes_list, news_items, cal_events = await asyncio.gather(quotes_task, news_task, calendar_task)

    # Update state
    for q in quotes_list:
        if q:
            state.quotes[q.symbol] = q

    state.news_items      = news_items
    state.calendar_events = cal_events

    # Fetch real account info from broker (used by risk manager for position sizing)
    if not settings.is_paper:
        try:
            from brokers.base import BrokerFactory, BrokerName
            factory = BrokerFactory(settings)
            broker = factory.get(BrokerName.MT5)
            if not broker.connected:
                await broker.connect()
            state.account_info = await broker.get_account()
            log.info("[DATA] Account: {} | Balance: {:.2f} {}",
                     state.account_info.broker, state.account_info.balance, state.account_info.currency)
        except Exception as e:
            log.warning("[DATA] Could not fetch account info: {} — using fallback balance", e)

    log.info("[DATA] {} quotes | {} news | {} calendar events loaded",
             len(state.quotes), len(state.news_items), len(state.calendar_events))

    state.messages.append(AgentMessage(
        from_agent="data_collector", to_agent="market_analyst",
        message_type="data_ready", payload={"symbols": list(state.quotes.keys())}
    ))
    return state


# ═══════════════════════════════════════════════════════
#  NODE: STRATEGY ADAPTER
# ═══════════════════════════════════════════════════════

# Singleton shared across cycles so accumulated history persists
_strategy_engine  = get_strategy_engine()
_perf_watchdog    = get_watchdog()

# Lazy import so we don't blow up if OutcomeTracker isn't instantiated yet
_outcome_tracker  = None


def _get_outcome_tracker():
    global _outcome_tracker
    if _outcome_tracker is None:
        from core.outcome_tracker import OutcomeTracker
        _outcome_tracker = OutcomeTracker()
    return _outcome_tracker


async def strategy_adapter_node(state: BotState) -> BotState:
    """
    Runs once per cycle, just after data_collector and before market_analyst.

    What it does:
      1. Determines current market regime (uses macro_data already in state,
         or defaults from market_regime field).
      2. Calls StrategyAdaptationEngine to build a live-performance-adapted
         StrategyProfile for this regime.
      3. Calls PerformanceWatchdog to detect degradation, missed signals,
         and hot/cold symbols.
      4. Writes both outputs into state.strategy_params so every downstream
         node can read them without a circular import.
      5. Logs a compact summary including any warnings.

    Downstream consumers:
      - market_analyst_node     → applies signal score adjustments
      - risk_manager_node       → uses regime-adapted min_adx / SL / TP
      - orchestrator_node       → injects watchdog report into LLM prompt
      - autonomous_orchestrator → injects profile thresholds into fast path
    """
    try:
        # Determine active regime
        regime = (
            state.market_regime
            or state.macro_data.get("macro_regime", "WEAK_TREND")
            or "WEAK_TREND"
        )

        tracker = _get_outcome_tracker()

        # ── Strategy profile ──────────────────────────────────────────────
        profile = _strategy_engine.get_adapted_profile(regime, tracker)

        # ── Watchdog report ───────────────────────────────────────────────
        watchdog_report = await _perf_watchdog.run(tracker, state)

        # Apply watchdog suggested adjustments on top of profile
        adj = watchdog_report.suggested_adjustments
        if adj:
            profile.score_adjustment      += adj.get("min_score_delta", 0.0)
            profile.confidence_adjustment += adj.get("min_confidence_delta", 0.0)
            profile.rr_adjustment         += adj.get("min_rr_delta", 0.0)
            # Clamp
            profile.score_adjustment      = max(-1.0, min(2.0, profile.score_adjustment))
            profile.confidence_adjustment = max(-0.10, min(0.20, profile.confidence_adjustment))
            profile.rr_adjustment         = max(-0.30, min(0.80, profile.rr_adjustment))

        # ── Serialise to state ────────────────────────────────────────────
        state.strategy_params = {
            "regime":                regime,
            "profile":               profile.to_dict(),
            "watchdog":              watchdog_report.to_dict(),
            "watchdog_summary":      watchdog_report.llm_summary(),
            # Flat convenience keys read directly by risk_manager_node:
            "min_adx":               profile.min_adx + adj.get("min_adx_delta", 0.0),
            "max_atr_ratio":         profile.max_atr_ratio,  # regime-aware ATR ceiling
            "sl_multiplier":         profile.sl_multiplier,
            "tp_multiplier":         profile.tp_multiplier,
            "effective_min_score":   profile.effective_min_score,
            "effective_min_conf":    profile.effective_min_confidence,
            "effective_min_rr":      profile.effective_min_rr,
            "preferred_strategies":  profile.preferred_strategies,
            "avoided_strategies":    profile.avoided_strategies,
            "symbol_score_delta":    profile.symbol_score_delta,
            "hot_symbols":           watchdog_report.hot_symbols,
            "cold_symbols":          watchdog_report.cold_symbols,
            "is_degraded":           watchdog_report.is_degraded,
            "alert_level":           watchdog_report.alert_level,
            "trigger_retraining":    watchdog_report.trigger_retraining,
        }

        log.info(
            "[STRATEGY_ADAPTER] Regime='{}' | src={} | WR={:.0%} n={} | "
            "eff_score≥{:.1f} eff_conf≥{:.0%} eff_RR≥{:.1f} | "
            "watchdog={}",
            regime,
            profile.source,
            profile.win_rate,
            profile.trade_count,
            profile.effective_min_score,
            profile.effective_min_confidence,
            profile.effective_min_rr,
            watchdog_report.alert_level,
        )

        # Log to activity for dashboard visibility
        if watchdog_report.alert_level in ("WARNING", "CRITICAL"):
            log.warning(
                "[STRATEGY_ADAPTER] {} — {}",
                watchdog_report.alert_level,
                watchdog_report.degradation_reason,
            )
        if watchdog_report.missed_count >= 3:
            log.warning(
                "[STRATEGY_ADAPTER] {} missed signals | top_reason='{}' | "
                "top_symbol={} | est_missed_pnl={:.2f}%",
                watchdog_report.missed_count,
                watchdog_report.top_miss_reason,
                watchdog_report.top_miss_symbol,
                watchdog_report.missed_total_pnl_pct,
            )

    except Exception as exc:
        log.error("[STRATEGY_ADAPTER] Failed — passing through: {}", exc)

    return state


# ═══════════════════════════════════════════════════════
#  NODE: MARKET ANALYST
# ═══════════════════════════════════════════════════════

async def market_analyst_node(state: BotState) -> BotState:
    """
    Technical analysis on all tracked symbols.
    Generates raw TradingSignal objects for promising setups.
    """
    log.info("[ANALYST] Scanning {} symbols for technical setups...", len(state.quotes))

    from strategies.technical import TechnicalAnalyser

    analyser = TechnicalAnalyser()
    new_signals: list[TradingSignal] = []

    for symbol, quote in state.quotes.items():
        try:
            signals = await analyser.analyse(symbol, quote)
            new_signals.extend(signals)
        except Exception as e:
            log.warning("MarketAnalyst error on {}: {}", symbol, e)

    # ── Apply strategy profile score adjustments ───────────────────────────
    # This boosts preferred strategies and penalises avoided ones based on
    # live regime performance, and applies per-symbol heat-map deltas.
    profile_dict = state.strategy_params.get("profile")
    if profile_dict and new_signals:
        from core.strategy_adaptation import StrategyProfile
        from dataclasses import fields as _dc_fields
        try:
            # Reconstruct StrategyProfile from stored dict for apply_signal_adjustments
            valid_keys = {f.name for f in _dc_fields(StrategyProfile)}
            filtered = {k: v for k, v in profile_dict.items() if k in valid_keys}
            # Convert last_updated string back to datetime if needed
            if isinstance(filtered.get("last_updated"), str):
                from datetime import datetime as _dt
                try:
                    filtered["last_updated"] = _dt.fromisoformat(filtered["last_updated"])
                except Exception:
                    filtered["last_updated"] = _dt.utcnow()
            tmp_profile = StrategyProfile(**filtered)
            new_signals = _strategy_engine.apply_signal_adjustments(new_signals, tmp_profile)
            log.info("[ANALYST] Strategy profile adjustments applied (regime={})",
                     profile_dict.get("regime", "?"))
        except Exception as _e:
            log.warning("[ANALYST] Could not apply strategy profile adjustments: {}", _e)

    # Sort by score descending
    new_signals.sort(key=lambda s: s.score, reverse=True)

    # Use regime-adapted min score if available, else fall back to config
    effective_min_score = state.strategy_params.get(
        "effective_min_score", settings.strategy.min_signal_score
    )
    # Keep top N to avoid noise
    top_signals = [s for s in new_signals if s.score >= effective_min_score][:5]
    log.info("[ANALYST] {} signals pass score≥{:.1f} gate (strategy-adapted)",
             len(top_signals), effective_min_score)
    
    # --- ReAct Reasoning Loop (BATCH mode — 1 LLM call for all signals) ---
    reasoned_signals = list(top_signals)  # default: keep originals

    if top_signals:
        log.info("[ANALYST] Applying ReAct batch reasoning to {} signals...", len(top_signals))

        # Build a compact batch payload — only fields the LLM needs
        signals_batch = []
        for i, sig in enumerate(top_signals):
            signals_batch.append({
                "id": i,
                "symbol": sig.symbol,
                "direction": sig.direction.value if hasattr(sig.direction, "value") else str(sig.direction),
                "timeframe": sig.timeframe,
                "indicators": sig.reasoning[:200],
                "rsi":  sig.metadata.get("rsi", 50),
                "adx":  sig.metadata.get("adx", 20),
                "fvg":  sig.metadata.get("fvg", False),
                "ob":   sig.metadata.get("order_block", False),
            })

        batch_system = (
            "You are a professional technical analyst. "
            "Evaluate each signal in the JSON array. "
            "Is it a high-probability trade or a liquidity trap? "
            "Return ONLY a JSON array with one object per signal in the SAME ORDER: "
            '[{"id":0,"confidence_score":0.0-10.0,"reasoning":"brief"}, ...]'
        )
        batch_user = json.dumps(signals_batch)

        try:
            resp = await call_llm(batch_system, batch_user, max_tokens=512, agent="market_analyst")

            if resp:
                clean = resp.strip()
                if clean.startswith("```"):
                    parts = clean.split("```")
                    clean = parts[1] if len(parts) > 1 else clean
                    if clean.startswith("json"):
                        clean = clean[4:]
                    clean = clean.strip()

                # Extract the JSON array
                arr_start = clean.find("[")
                arr_end   = clean.rfind("]") + 1
                if arr_start != -1 and arr_end > arr_start:
                    analyses = json.loads(clean[arr_start:arr_end])
                    for item in analyses:
                        idx = item.get("id", -1)
                        if not isinstance(item, dict) or not (0 <= idx < len(top_signals)):
                            continue
                        top_signals[idx].score = float(item.get("confidence_score", top_signals[idx].score))
                        top_signals[idx].reasoning += f" | ReAct: {item.get('reasoning', '')}"
                        log.info("[ANALYST] [ReAct] {} {} | Score:{} | {}",
                                 top_signals[idx].direction, top_signals[idx].symbol,
                                 top_signals[idx].score, item.get("reasoning", ""))
                    reasoned_signals = list(top_signals)
                    log.info("[ANALYST] ReAct batch complete — {} signals updated", len(analyses))
                else:
                    log.warning("[ANALYST] ReAct: no JSON array found in response — using original scores")
            else:
                log.warning("[ANALYST] ReAct: empty LLM response — using original scores")

        except Exception as e:
            log.warning("[ANALYST] ReAct batch failed: {} — using original scores", e)

    state.pending_signals = reasoned_signals
    return state


# ═══════════════════════════════════════════════════════
#  NODE: SENTIMENT AGENT
# ═══════════════════════════════════════════════════════

async def sentiment_agent_node(state: BotState) -> BotState:
    """
    NLP analysis of news items.
    Updates signal confidence scores based on sentiment alignment.
    Uses LLM to classify geopolitical impact on each asset class.
    """
    if not state.pending_signals:
        return state

    log.info("[SENTIMENT] Analysing {} news items against {} signals...",
             len(state.news_items), len(state.pending_signals))

    if not state.news_items:
        return state

    # Build news summary for LLM
    news_summary = "\n".join([
        f"- [{n.source}] {n.title} (sentiment: {n.sentiment:.2f})"
        for n in state.news_items[:20]
    ])

    signals_summary = "\n".join([
        f"- {s.direction} {s.symbol} (score:{s.score:.1f})"
        for s in state.pending_signals
    ])

    system_prompt = """You are a financial news sentiment analyst for an algorithmic trading system.
    Analyse the latest news and assess whether it supports or contradicts each pending trade signal.
    Return ONLY a valid JSON array with adjustments.
    Format: [{"symbol": "XAUUSD", "sentiment_boost": 0.08, "reasoning": "brief reason"}]
    sentiment_boost ranges from -0.3 (strong contra) to +0.3 (strong support). Be concise."""

    user_prompt = f"""Latest News:\n{news_summary}\n\nPending Signals:\n{signals_summary}\n
    For each signal, provide a sentiment_boost based on news alignment. Return JSON array only."""

    try:
        from agents.memory import memory
        # Search for similar past GEOPOLITICAL contexts to provide 'experience' to the LLM
        past_events = memory.search_similar_events(news_summary, n_results=5)
        past_context = ""
        if past_events:
            past_context = "\n\nSimilar Past Geopolitical Events for Reference:\n" + "\n".join([
                f"- Event: {e.get('context', '')[:300]}... | Sentiment Alignment: {e.get('metadata', {}).get('sentiment', 'N/A')}"
                for e in past_events if isinstance(e, dict) and 'context' in e
            ])

        response = await call_llm(system_prompt, user_prompt + past_context, max_tokens=512, agent="sentiment_agent")
        # Parse JSON (strip any markdown fences)
        clean = response.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
            clean = clean.strip()
        data = json.loads(clean)

        # Robustness: LLM sometimes returns a dict with a key like "adjustments"
        # instead of a raw array, or it wraps the array in another object.
        adjustments = []
        if isinstance(data, list):
            adjustments = data
        elif isinstance(data, dict):
            # Try to find a list field within the dict
            for val in data.values():
                if isinstance(val, list):
                    adjustments = val
                    break
        
        if not adjustments:
            log.warning("SentimentAgent: LLM returned no valid adjustments or unexpected format: {}", clean[:200])
            return state

        boost_map = {a["symbol"]: a for a in adjustments if isinstance(a, dict) and "symbol" in a}
        for signal in state.pending_signals:
            if signal.symbol in boost_map:
                adj = boost_map[signal.symbol]
                old_conf = signal.confidence
                # Ensure it's a number
                boost = adj.get("sentiment_boost", 0)
                if not isinstance(boost, (int, float)):
                    boost = float(boost) if str(boost).replace('.','',1).isdigit() else 0.0
                
                signal.confidence = min(1.0, max(0.0, signal.confidence + boost))
                signal.reasoning += f" | Sentiment: {adj.get('reasoning', '')}"
                log.info("[SENTIMENT] {} confidence {:.0f}% → {:.0f}%",
                         signal.symbol, old_conf*100, signal.confidence*100)

        # Persist for dashboard
        try:
            db_store = DuckDBStore(settings.training.duckdb_path)
            await db_store.start()
            await db_store.log_sentiment_analysis(news_summary, adjustments)
            await db_store.stop()
        except Exception as db_err:
            log.warning("Failed to log sentiment analysis to DB: {}", db_err)

    except Exception as e:
        log.warning("SentimentAgent error: {}", e)

    return state


# ═══════════════════════════════════════════════════════
#  NODE: CALENDAR AGENT
# ═══════════════════════════════════════════════════════

async def calendar_agent_node(state: BotState) -> BotState:
    """
    Checks upcoming economic events.
    Sets state.is_news_blackout and filters/warns on signals.
    """
    log.info("[CALENDAR] Checking {} upcoming events...", len(state.calendar_events))

    now = datetime.utcnow()
    cfg = settings.risk

    state.is_news_blackout = False

    for event in state.calendar_events:
        if event.released:
            continue
        minutes_to_event = (event.scheduled - now).total_seconds() / 60

        if event.impact == NewsImpact.HIGH:
            before_window = cfg.blackout_before_high_impact
            after_window  = cfg.blackout_after_high_impact
        elif event.impact == NewsImpact.MEDIUM:
            before_window = cfg.blackout_before_med_impact
            after_window  = cfg.blackout_after_med_impact
        else:
            continue

        if -after_window <= minutes_to_event <= before_window:
            state.is_news_blackout = True
            log.warning("[CALENDAR] BLACKOUT ACTIVE — '{}' in {:.0f}min ({})",
                        event.title, minutes_to_event, event.currency)
            event.bot_action = "PAUSE_TRADING"

        elif 0 < minutes_to_event <= 60:
            log.info("[CALENDAR] '{}' in {:.0f}min — TIGHTENING SL on {} pairs",
                     event.title, minutes_to_event, event.currency[:3])
            # Remove signals for affected currency
            state.pending_signals = [
                s for s in state.pending_signals
                if event.currency[:3] not in s.symbol
            ]

    if state.is_news_blackout:
        log.warning("[CALENDAR] ALL signals SUPPRESSED during news blackout")
        state.pending_signals = []

    return state


# ═══════════════════════════════════════════════════════
#  NODE: MACRO AGENT
# ═══════════════════════════════════════════════════════

async def macro_agent_node(state: BotState) -> BotState:
    """
    Fetches DXY and US10Y data.
    Populates state.macro_data.
    """
    log.info("[MACRO] Fetching global macro indicators...")
    try:
        from agents.macro_agent import MacroAgent
        agent = MacroAgent()
        state.macro_data = await agent.get_macro_sentiment()
        log.info("[MACRO] DXY trend: {}, Yield trend: {}", 
                 state.macro_data.get("dxy_trend"), state.macro_data.get("yield_trend"))
    except Exception as e:
        log.error("🌎 MacroAgent: Failed to fetch macro data: {}", e)
        state.macro_data = {"dxy_trend": "FLAT", "yield_trend": "FLAT"}
    return state


# ═══════════════════════════════════════════════════════
#  NODE: RISK MANAGER
# ═══════════════════════════════════════════════════════

async def risk_manager_node(state: BotState) -> BotState:
    """
    SOP Section 01 — Signal Quality Gates (G1-G10).
    SOP Section 06 — Half-Kelly position sizing with regime multipliers.
    SOP Section 08 — Correlation & portfolio rules.
    All 10 gates must pass. Any failure = rejection (HARD VETO).
    """
    log.info("[RISK] Evaluating {} signals against {} open trades...",
             len(state.pending_signals), len(state.open_trades))

    cfg = settings.risk
    approved: list[TradingSignal] = []

    account_balance = state.account_info.balance if state.account_info else 50_000.0
    account_equity  = state.account_info.equity  if state.account_info else account_balance
    open_count = len(state.open_trades)

    # ── Pull regime-adapted gates from strategy_params (set by strategy_adapter_node)
    sp = state.strategy_params
    _eff_min_score   = sp.get("effective_min_score", cfg.min_signal_score)
    _eff_min_conf    = sp.get("effective_min_conf",  cfg.min_confidence)
    _eff_min_rr      = sp.get("effective_min_rr",    cfg.min_risk_reward)
    _eff_min_adx     = sp.get("min_adx",             cfg.min_adx)
    _eff_max_atr     = sp.get("max_atr_ratio",       cfg.max_atr_ratio)  # regime-aware ATR ceiling
    _sl_mult_ovr     = sp.get("sl_multiplier",        None)   # None = use REGIME dict
    _tp_mult_ovr     = sp.get("tp_multiplier",        None)   # None = use REGIME dict
    if sp:
        log.info(
            "[RISK] Strategy-adapted gates: score≥{:.1f} conf≥{:.0%} RR≥{:.1f} ADX≥{:.0f} ATR≤{:.1f}",
            _eff_min_score, _eff_min_conf, _eff_min_rr, _eff_min_adx, _eff_max_atr,
        )

    # ── G9: Daily drawdown — HARD VETO ─────────────────────────────────────
    daily_loss = sum(
        getattr(t, "pnl", 0.0) for t in state.open_trades
        if getattr(t, "close_time", None) and t.close_time.date() == datetime.utcnow().date()
    )
    if daily_loss < -(account_balance * cfg.max_daily_drawdown_pct / 100):
        log.warning("[RISK] HARD VETO G9 — Daily drawdown {:.2f}% reached (${:.2f})",
                    cfg.max_daily_drawdown_pct, daily_loss)
        state.pending_signals = []
        return state

    # ── Equity floor check — HARD VETO ─────────────────────────────────────
    peak_balance = state.metadata.get("peak_balance", account_balance) if hasattr(state, "metadata") else account_balance
    if account_equity < peak_balance * (cfg.min_equity_pct / 100):
        log.warning("[RISK] HARD VETO — Equity {:.2f} below {}% of peak {:.2f}",
                    account_equity, cfg.min_equity_pct, peak_balance)
        state.pending_signals = []
        return state

    # ── G10: Max open trades — HARD VETO ───────────────────────────────────
    if open_count >= cfg.max_open_trades:
        log.warning("[RISK] HARD VETO G10 — Max open trades ({}) reached", cfg.max_open_trades)
        state.pending_signals = []
        return state

    # ── Consecutive losses — pause gate ────────────────────────────────────
    consec_losses = state.metadata.get("consecutive_losses", 0) if hasattr(state, "metadata") else 0
    if consec_losses >= cfg.max_consecutive_losses:
        log.warning("[RISK] HARD VETO — {} consecutive losses, 4h pause active", consec_losses)
        state.pending_signals = []
        return state

    # ── Pre-compute combined open risk ─────────────────────────────────────
    from strategies.technical import _point_value as _pv
    combined_open_risk = sum(
        getattr(t, "lot_size", 0.01) *
        abs(getattr(t, "entry_price", 0.0) - getattr(t, "stop_loss", 0.0)) *
        _pv(getattr(t, "symbol", "XAUUSD"))
        for t in state.open_trades
    )
    
    # Log existing risk usage for transparency
    if combined_open_risk > 0:
        risk_pct = (combined_open_risk / account_balance * 100) if account_balance > 0 else 0
        log.info("[RISK] Existing open trades using ${:.0f} ({:.1f}% of account) from {} positions",
                 combined_open_risk, risk_pct, len(state.open_trades))

    # ── Drawdown scaling (P-04: scale 50% if down 5% from peak) ────────────
    dd_from_peak = (peak_balance - account_equity) / peak_balance if peak_balance > 0 else 0.0
    drawdown_scale = 0.5 if dd_from_peak >= cfg.drawdown_scale_threshold_pct / 100 else 1.0

    regime = state.market_regime or "WEAK_TREND"

    # ── PRIORITIZE SIGNALS BY QUALITY ──────────────────────────────────────
    # Sort signals by quality score (confidence * score) so best signals get budget first
    state.pending_signals = sorted(
        state.pending_signals,
        key=lambda s: (s.confidence * s.score),
        reverse=True  # Highest quality first
    )
    log.info("[RISK] Prioritized {} signals by quality (conf × score)", len(state.pending_signals))

    for signal in state.pending_signals:
        reject: list[str] = []

        # G1 — Minimum signal score (regime-adapted)
        if signal.score < _eff_min_score:
            reject.append(f"G1: score {signal.score:.1f} < {_eff_min_score:.1f}")

        # G2 — Minimum confidence (regime-adapted)
        if signal.confidence < _eff_min_conf:
            reject.append(f"G2: confidence {signal.confidence:.0%} < {_eff_min_conf:.0%}")

        # G3 — Minimum R:R (regime-adapted)
        if signal.risk_reward < _eff_min_rr:
            reject.append(f"G3: R:R {signal.risk_reward:.2f} < {_eff_min_rr:.2f}")

        # G4 — ADX trend filter (regime-adapted; set to 0.0 in RANGING so gate is skipped)
        adx = signal.metadata.get("adx", 0.0)
        if _eff_min_adx > 0 and adx < _eff_min_adx:
            reject.append(f"G4: ADX {adx:.1f} < {_eff_min_adx:.0f} (too choppy)")

        # G5 — ATR volatility filter (upper cap uses regime-adapted value from strategy profile)
        # e.g. HIGH_VOLATILE profile sets max_atr_ratio=2.8 vs base config 2.0,
        # so gold signals during news volatility spikes are not incorrectly rejected.
        atr_ratio = signal.metadata.get("atr_ratio", 1.0)
        if atr_ratio < cfg.min_atr_ratio:
            reject.append(f"G5: ATR ratio {atr_ratio:.2f} < {cfg.min_atr_ratio} (low vol)")
        elif atr_ratio > _eff_max_atr:
            reject.append(f"G5: ATR ratio {atr_ratio:.2f} > {_eff_max_atr:.1f} (excessive vol)")

        # G6 — Volume confirmation (scale down instead of reject if below threshold)
        vol_ratio = signal.metadata.get("volume_ratio", 1.0)
        volume_scale = 1.0
        if vol_ratio < cfg.min_volume_ratio:
            # Scale position size based on volume ratio instead of rejecting
            # If vol_ratio is 0.5 and min is 0.8, scale to 0.625 (0.5/0.8)
            volume_scale = vol_ratio / cfg.min_volume_ratio
            log.info("[RISK] VOLUME SCALE {} {} — vol ratio {:.2f} < {:.2f}, scaling position by {:.2f}x", 
                     signal.direction, signal.symbol, vol_ratio, cfg.min_volume_ratio, volume_scale)

        # G7 — News blackout (already managed by calendar_agent, check flag)
        if state.is_news_blackout:
            reject.append("G7: news blackout active")

        # G8 — Macro regime veto (direction-aware for metals & commodities)
        macro_regime = state.macro_data.get("macro_regime", "NEUTRAL")
        dxy_change   = state.macro_data.get("dxy_change", 0.0)
        sig_dir      = signal.direction.value if hasattr(signal.direction, "value") else signal.direction
        sym_upper    = signal.symbol.upper()

        _g8_veto = False
        if macro_regime == "SEVERE_RISK_OFF":
            _g8_veto = True
        elif dxy_change > 0.8:
            # DXY rising hard (USD strengthening).
            # For USD-inverse assets (gold, silver, EUR pairs), a rising DXY is
            # bearish — so veto BUY signals only, never SELL signals.
            _is_dxy_inverse = any(pfx in sym_upper for pfx in ("XAU", "XAG", "XPT", "EUR", "GBP", "AUD", "NZD"))
            if _is_dxy_inverse:
                if sig_dir == "BUY":
                    _g8_veto = True   # USD strong = gold/EUR BUY is fighting the macro
                # SELL on gold/EUR during USD strength = VALID trade → do NOT veto
            else:
                _g8_veto = True       # for other assets veto both directions during extreme DXY

        if _g8_veto:
            reject.append(f"G8: macro {macro_regime} / DXY change {dxy_change:.2f}% dir={sig_dir}")

        # G9 already checked above (daily drawdown VETO stops all signals)

        # G10 — Open trade cap (per-signal slot check)
        if len(approved) + open_count >= cfg.max_open_trades:
            reject.append(f"G10: max trades {cfg.max_open_trades} would be exceeded")

        # ── Per-symbol cap (max 2 positions per symbol) ─────────────────────
        sym_count = sum(1 for t in state.open_trades if t.symbol == signal.symbol)
        if sym_count >= cfg.max_trades_per_symbol:
            reject.append(f"symbol cap: {sym_count} already open on {signal.symbol}")

        # ── No opposing direction on same symbol ────────────────────────────
        open_dir = next((t.direction for t in state.open_trades if t.symbol == signal.symbol), None)
        if open_dir and open_dir != signal.direction:
            reject.append(f"opposing direction already open on {signal.symbol}")

        # ── SOP Section 08 — Correlation group check ────────────────────────
        corr_reject = _check_correlation(signal, state.open_trades)
        if corr_reject:
            reject.append(corr_reject)

        # ── P-03: Combined open risk cap ────────────────────────────────────
        signal_sl_dist = abs(signal.entry_price - signal.stop_loss)
        lot = _calculate_lot_size(signal, cfg, account_balance, regime, drawdown_scale)
        trade_risk = lot * signal_sl_dist * _pv(signal.symbol)
        
        # Calculate available risk budget
        max_allowed_risk = account_balance * (cfg.max_combined_risk_pct / 100)
        available_risk = max_allowed_risk - combined_open_risk
        
        # If trade risk exceeds available budget, scale down position size instead of rejecting
        if trade_risk > available_risk:
            if available_risk > 0:
                # Scale down the lot size to fit within available risk
                scale_factor = available_risk / trade_risk
                lot = lot * scale_factor
                trade_risk = available_risk
                log.info("[RISK] SCALED {} {} — reduced lot from {:.2f} to {:.2f} (available risk: ${:.0f})", 
                         signal.direction, signal.symbol, 
                         _calculate_lot_size(signal, cfg, account_balance, regime, drawdown_scale),
                         lot, available_risk)
            else:
                # No risk budget available at all
                reject.append(f"P-03: combined open risk {combined_open_risk:.0f} already at {cfg.max_combined_risk_pct}% cap (no budget available)")

        if reject:
            log.info("[RISK] REJECTED {} {} — {}", signal.direction, signal.symbol, "; ".join(reject))
            continue

        # ── Size the position (Half-Kelly + tranches) ───────────────────────
        # Apply volume scaling and risk scaling to the calculated lot size
        total_lots  = lot  # Use the already scaled lot from risk check
        
        # Apply volume scale if needed
        if volume_scale < 1.0:
            total_lots = total_lots * volume_scale
        
        lots_t1 = round(total_lots * 0.40, 2)
        lots_t2 = round(total_lots * 0.35, 2)
        lots_t3 = round(total_lots * 0.25, 2)

        signal.metadata["lot_size"]  = max(lots_t1, 0.01)   # T1 placed now
        signal.metadata["lots_t1"]   = max(lots_t1, 0.01)
        signal.metadata["lots_t2"]   = max(lots_t2, 0.01)
        signal.metadata["lots_t3"]   = max(lots_t3, 0.01)
        signal.metadata["tranche"]   = "T1"

        # SL/TP by regime — prefer strategy_params override, fall back to config dict
        atr = signal.metadata.get("atr", signal_sl_dist / 1.5)
        sl_mult = _sl_mult_ovr if _sl_mult_ovr is not None else REGIME_SL_MULTIPLIERS.get(regime, 1.5)
        tp_mult = _tp_mult_ovr if _tp_mult_ovr is not None else REGIME_TP_MULTIPLIERS.get(regime, 2.5)
        sl_dist = max(atr * sl_mult, atr * 0.5)      # min 0.5 ATR
        tp_dist = sl_dist * tp_mult
        if tp_dist / sl_dist < 1.8:
            log.warning("[RISK] {} R:R {:.2f} below 1.8 after regime adjustment — skipping",
                        signal.symbol, tp_dist / sl_dist)
            continue

        if signal.direction == Direction.BUY or signal.direction == "BUY":
            signal.stop_loss   = signal.entry_price - sl_dist
            signal.take_profit = signal.entry_price + tp_dist
        else:
            signal.stop_loss   = signal.entry_price + sl_dist
            signal.take_profit = signal.entry_price - tp_dist

        signal.metadata["regime"]    = regime
        signal.metadata["atr"]       = atr
        signal.metadata["sl_dist"]   = sl_dist
        signal.metadata["tp_t1"]     = signal.take_profit
        signal.metadata["tp_t2"]     = (
            signal.entry_price + atr * 3.5 if signal.direction in (Direction.BUY, "BUY")
            else signal.entry_price - atr * 3.5
        )
        signal.metadata["tp_t3"]     = (
            signal.entry_price + atr * 5.5 if signal.direction in (Direction.BUY, "BUY")
            else signal.entry_price - atr * 5.5
        )

        combined_open_risk += trade_risk
        approved.append(signal)
        log.info("[RISK] APPROVED {} {} | T1:{} T2:{} T3:{} lots | R:R {:.1f} | regime:{}",
                 signal.direction, signal.symbol, lots_t1, lots_t2, lots_t3,
                 signal.risk_reward, regime)

    state.approved_signals = approved
    log.info("[RISK] {}/{} signals approved (SOP gates G1-G10)", len(approved), len(state.pending_signals))
    return state


def _check_correlation(signal: TradingSignal, open_trades: list) -> str | None:
    """SOP Section 08 — check correlation group limits. Returns reject reason or None."""
    sym = signal.symbol.upper()
    for group_name, (symbols, max_pos) in CORRELATION_GROUPS.items():
        if not any(s in sym or sym in s for s in symbols):
            continue
        # Count same-direction open trades in this group
        same_dir = sum(
            1 for t in open_trades
            if any(s in t.symbol.upper() or t.symbol.upper() in s for s in symbols)
            and t.direction == signal.direction
        )
        if same_dir >= max_pos:
            return f"correlation group {group_name}: {same_dir}/{max_pos} positions open"
    return None


def _calculate_lot_size(
    signal: TradingSignal,
    cfg,
    account_balance: float = 50_000.0,
    regime: str = "WEAK_TREND",
    drawdown_scale: float = 1.0,
) -> float:
    """
    SOP Section 06 — Half-Kelly position sizing.
    half_kelly = (win_rate - (1-win_rate)/avg_rr) × 0.5
    Apply regime multiplier and hard 2% cap.
    """
    win_rate = signal.confidence          # proxy: LLM/model confidence
    avg_rr   = max(signal.risk_reward, 1.0)

    kelly_f  = win_rate - ((1 - win_rate) / avg_rr)
    half_k   = max(kelly_f, 0.0) * 0.5

    regime_mult = REGIME_RISK_MULTIPLIERS.get(regime, 1.0)
    risk_pct    = half_k * regime_mult * drawdown_scale

    # Hard cap: 2% per trade (SOP Section 6.3)
    risk_pct = min(risk_pct, cfg.max_risk_per_trade_pct / 100)

    risk_amount = account_balance * risk_pct
    sl_distance = abs(signal.entry_price - signal.stop_loss)
    if sl_distance == 0:
        return 0.01

    from strategies.technical import _point_value
    pv = _point_value(signal.symbol)
    raw_lot = risk_amount / (sl_distance * pv)

    return round(min(raw_lot, cfg.max_lot_size), 2)


# ═══════════════════════════════════════════════════════
#  NODE: ORCHESTRATOR (LLM final decision)
# ═══════════════════════════════════════════════════════

async def orchestrator_node(state: BotState) -> BotState:
    """
    The master brain. Makes final trade approval using autonomous fast path + LLM.
    Considers: approved signals, market regime, open portfolio, news context.
    """
    import time
    
    if not state.approved_signals:
        log.info("[ORCHESTRATOR] No approved signals to evaluate")
        return state

    # Check if autonomous mode is enabled
    use_autonomous = getattr(settings, "use_autonomous_orchestrator", True)
    
    if use_autonomous:
        log.info("[ORCHESTRATOR] Using autonomous fast path for {} signals...", len(state.approved_signals))
        from agents.autonomous_orchestrator import AutonomousOrchestrator
        
        # Get or create singleton instance
        if not hasattr(orchestrator_node, "_autonomous"):
            orchestrator_node._autonomous = AutonomousOrchestrator()
        
        autonomous = orchestrator_node._autonomous
        state = await autonomous.process_signals(state)
        
        # Log to DuckDB for training
        from memory.duckdb_store import DuckDBStore
        store = DuckDBStore(settings.training.duckdb_path)
        await store.start()
        await store.init_schema()
        
        for signal in state.approved_signals:
            await store.log_decision(
                timestamp=datetime.utcnow(),
                symbol=signal.symbol,
                context={
                    "symbol": signal.symbol,
                    "direction": signal.direction.value if hasattr(signal.direction, "value") else signal.direction,
                    "score": signal.score,
                    "confidence": signal.confidence,
                    "rsi": signal.metadata.get("rsi", 50),
                    "adx": signal.metadata.get("adx", 20),
                    "atr_pct": signal.metadata.get("atr_pct", 0.0),
                    "regime": state.market_regime,
                    "decision": "APPROVE",
                    "reasoning": "Autonomous orchestrator approved"
                },
                outcome=None,
                final_pnl=None
            )
        
        await store.stop()
        return state
    
    # Fallback to original LLM-based orchestrator
    log.info("[ORCHESTRATOR] LLM evaluating {} approved signals...", len(state.approved_signals))
    
    # Track decision timing
    decision_start_time = time.time()

    # Watchdog + strategy adaptation context (from strategy_adapter_node)
    watchdog_summary = state.strategy_params.get("watchdog_summary", "")
    strategy_regime  = state.strategy_params.get("regime", state.market_regime or "UNKNOWN")
    pref_strats  = state.strategy_params.get("preferred_strategies", [])
    avoid_strats = state.strategy_params.get("avoided_strategies", [])
    hot_syms     = state.strategy_params.get("hot_symbols", [])
    cold_syms    = state.strategy_params.get("cold_symbols", [])

    portfolio_summary = f"""
    Open trades: {len(state.open_trades)}
    Market regime: {state.market_regime}
    Strategy regime: {strategy_regime}
    News blackout: {state.is_news_blackout}
    Recent news sentiment: {_summarise_news(state.news_items[:5])}
    Preferred strategies this regime: {pref_strats or 'any'}
    Avoided strategies this regime: {avoid_strats or 'none'}
    Hot symbols (overperforming): {hot_syms or 'none'}
    Cold symbols (underperforming): {cold_syms or 'none'}
    {watchdog_summary}
    """

    signals_detail = json.dumps([{
        "symbol":            s.symbol,
        "direction":         s.direction,
        "score":             s.score,
        "confidence":        s.confidence,
        "strategy":          s.strategy,
        "rr":                s.risk_reward,
        "reasoning":         s.reasoning[:200],
        "corr_boost":        s.metadata.get("correlation_boost", 0),
        "corr_confirms":     s.metadata.get("corr_confirmations", 0),
        "corr_contradicts":  s.metadata.get("corr_contradictions", 0),
        "leading_warnings":  s.metadata.get("leading_warnings", []),
        "is_divergence":     s.metadata.get("source") == "divergence_detector",
        "divergence_leader": s.metadata.get("leader", ""),
    } for s in state.approved_signals], indent=2)

    # Build per-signal correlation summaries for LLM context
    corr_summaries = "\n\n".join(
        build_correlation_summary(s) for s in state.approved_signals
    )

    try:
        # If using local fine-tuned model, we iterate through signals 1-by-1 
        # as it was trained on GO/NOGO single-input completion.
        use_simple_format = (settings.llm_provider == "local")
        
        decisions = []
        
        if use_simple_format:
            log.info("[ORCHESTRATOR] Using fine-tuned GO/NOGO parallel mode")
            from scripts.prepare_training_data import INSTRUCTION, format_input

            async def _score_one(s):
                ctx = {
                    "symbol":       s.symbol,
                    "direction":    s.direction.value if hasattr(s.direction, "value") else s.direction,
                    "score":        s.score,
                    "confidence":   s.confidence,
                    "rsi":          s.metadata.get("rsi", 50),
                    "adx":          s.metadata.get("adx", 20),
                    "atr_pct":      s.metadata.get("atr_pct", 0.0),
                    "regime":       state.market_regime,
                    "dxy_change":   state.macro_data.get("dxy_change", 0.0),
                    "us10y_change": state.macro_data.get("us10y_change", 0.0),
                    "macro_regime": state.macro_data.get("macro_regime", "NEUTRAL"),
                    "avg_sentiment":s.metadata.get("avg_sentiment", 0.0),
                    "news_summary": [n.title for n in state.news_items[:3]],
                }
                user_inp = format_input(ctx)
                resp = await call_llm(INSTRUCTION, user_inp, max_tokens=16, agent="orchestrator")
                decision_text = (resp or "").strip().upper()
                is_go = "GO" in decision_text and "NOGO" not in decision_text
                return {
                    "symbol":    s.symbol,
                    "direction": s.direction,
                    "decision":  "APPROVE" if is_go else "REJECT",
                    "reason":    "Fine-tuned decision" if is_go else "Rejected by fine-tuned model",
                }

            results = await asyncio.gather(
                *[_score_one(s) for s in state.approved_signals],
                return_exceptions=True,
            )
            for r in results:
                if isinstance(r, Exception):
                    log.warning("[ORCHESTRATOR] Signal parallel score failed: {}", r)
                else:
                    decisions.append(r)
        else:
            # Standard Batch JSON mode for Claude/GPT/Groq
            system_prompt = """You are the master orchestrator of an algorithmic trading system.
            Your role is to make the final APPROVE or REJECT decision on trade signals.

            PAY CLOSE ATTENTION to correlation data:
            - corr_boost > +1.0  : multiple assets confirm this move — strong conviction
            - corr_boost 0 to +1 : mild confirmation — proceed if technicals are solid
            - corr_boost < 0     : assets are contradicting — be very cautious
            - leading_warnings   : leaders haven't moved yet — signal may be premature
            - is_divergence=true : catch-up signal — leader moved, lagger hasn't yet

            PAY CLOSE ATTENTION to performance context:
            - Preferred strategies are statistically outperforming in the current regime — favour them
            - Avoided strategies are underperforming — be extra critical before approving
            - Hot symbols have strong recent win rates — modest conviction boost allowed
            - Cold symbols are in drawdown — demand higher confidence before approving
            - If WATCHDOG shows DEGRADATION or CRITICAL, tighten your approval threshold significantly
            - If WATCHDOG shows missed signals, consider whether the top miss reason applies here

            Consider: signal quality, correlation alignment, portfolio context, market conditions,
            performance watchdog alerts, and strategy regime data.
            Be selective — only approve high-conviction signals.
            Return ONLY a JSON array: [{"symbol": "XAUUSD", "direction": "BUY", "decision": "APPROVE", "reason": "brief"}]"""

            user_prompt = f"""Portfolio Context:\n{portfolio_summary}

Correlation Analysis:\n{corr_summaries}

Signals for Review:\n{signals_detail}

Make final trade decisions. Correlation alignment is a key factor. Return JSON only."""

            try:
                response = await call_llm(system_prompt, user_prompt, max_tokens=768, agent="orchestrator")
                clean = response.strip()
                if clean.startswith("```"):
                    clean = clean.split("```")[1]
                    if clean.startswith("json"):
                        clean = clean[4:]
                    clean = clean.strip()
                data = json.loads(clean)

                if isinstance(data, list):
                    decisions = data
                elif isinstance(data, dict):
                    for val in data.values():
                        if isinstance(val, list):
                            decisions = val
                            break
            except Exception as e:
                log.warning("[ORCHESTRATOR] JSON Decision fallback error: {}", e)
                # Pass through if something fails
                decisions = []

        if not decisions and state.approved_signals:
            log.warning("[ORCHESTRATOR] could not obtain decisions — passing approved signals")
            return state

        decision_map = {(d["symbol"], d["direction"]): d for d in decisions if isinstance(d, dict) and "symbol" in d}
        final_approved = []

        from agents.macro_agent import MacroAgent
        macro_agent = MacroAgent()
        
        # Persistent storage for training data
        from memory.duckdb_store import DuckDBStore
        store = DuckDBStore(settings.training.duckdb_path)
        await store.start()
        await store.init_schema()
        
        for signal in state.pending_signals:  # Iterate over ALL signals, not just approved_signals
            # Resolve decision from LLM map
            key = (signal.symbol, signal.direction)
            decision = decision_map.get(key, {})
            is_approved = decision.get("decision") == "APPROVE"

            # Apply Macro Veto for Gold (only if approved)
            if is_approved and "XAU" in signal.symbol.upper():
                is_vetoed, veto_reason = macro_agent.evaluate_veto(signal.symbol, signal.direction, state.macro_data)
                if is_vetoed:
                    log.warning("[ORCHESTRATOR] MACRO VETO for {} {} — {}", signal.direction, signal.symbol, veto_reason)
                    is_approved = False
                    decision["reason"] = f"MACRO VETO: {veto_reason}"

            # Log decision to DuckDB for future fine-tuning
            await store.log_decision(
                timestamp=datetime.utcnow(),
                symbol=signal.symbol,
                context={
                    "symbol": signal.symbol,
                    "direction": signal.direction.value if hasattr(signal.direction, "value") else signal.direction,
                    "score": signal.score,
                    "confidence": signal.confidence,
                    "rsi": signal.metadata.get("rsi", 50),
                    "adx": signal.metadata.get("adx", 20),
                    "atr_pct": signal.metadata.get("atr_pct", 0.0),
                    "regime": state.market_regime,
                    "dxy_change": state.macro_data.get("dxy_change", 0.0),
                    "us10y_change": state.macro_data.get("us10y_change", 0.0),
                    "macro_regime": state.macro_data.get("macro_regime", "NEUTRAL"),
                    "avg_sentiment": signal.metadata.get("avg_sentiment", 0.0),
                    "news_summary": signal.metadata.get("news_summary", []),
                    "decision": "APPROVE" if is_approved else "REJECT",
                    "reasoning": decision.get("reason", "No reason provided")
                },
                outcome=None if is_approved else "REJECTED",
                final_pnl=None if is_approved else 0.0
            )
            
            # Also log to bot_decisions table for Apex Health monitoring
            try:
                decision_time_ms = int((time.time() - decision_start_time) * 1000)
                await store.execute_write("""
                    INSERT INTO bot_decisions 
                    (timestamp, symbol, decision, confidence, outcome, decision_time_ms)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, [
                    datetime.utcnow(),
                    signal.symbol,
                    "GO" if is_approved else "NOGO",
                    signal.confidence,
                    None,  # Will be updated when trade closes
                    decision_time_ms
                ])
            except Exception as log_err:
                log.debug("Failed to log bot_decision: {}", log_err)

            if is_approved:
                signal.reasoning += f" | Orchestrator: {decision.get('reason','')}"
                final_approved.append(signal)
                log.info("[ORCHESTRATOR] APPROVED {} {} — {}", signal.direction, signal.symbol, decision.get("reason",""))
            else:
                log.info("[ORCHESTRATOR] REJECTED {} {} — {}", signal.direction, signal.symbol, decision.get("reason","no reason"))

        state.approved_signals = final_approved
        await store.stop()

    except Exception as e:
        log.warning("Orchestrator LLM error: {} — passing all approved signals", e)

    return state


def _summarise_news(items) -> str:
    if not items:
        return "No recent news"
    return "; ".join([f"{n.title[:60]}(sentiment:{n.sentiment:.1f})" for n in items])


# ═══════════════════════════════════════════════════════
#  NODE: EXECUTION AGENT
# ═══════════════════════════════════════════════════════

async def execution_agent_node(state: BotState, broker_factory=None) -> BotState:
    """
    Places approved signals as real (or paper) orders via the broker layer.
    """
    if not state.approved_signals:
        log.info("[EXEC] No signals to execute")
        return state

    log.info("[EXEC] Executing {} approved signals...", len(state.approved_signals))

    if settings.monitor_only:
        log.info("👀 MONITOR MODE: Skipping real order execution for {} signals.", len(state.approved_signals))
        # Log signals that would have been executed
        for signal in state.approved_signals:
            log.info("📊 VIRTUAL EXECUTION: {} {} @ {}", signal.direction, signal.symbol, signal.entry_price)
        return state

    from brokers.base import BrokerFactory, BrokerName
    factory = broker_factory or BrokerFactory(settings)

    for signal in state.approved_signals:
        # Route to correct broker based on asset class
        if signal.asset_class == AssetClass.CRYPTO:
            try:
                broker = factory.get(BrokerName.CCXT)
            except Exception:
                broker = factory.get(BrokerName.MT5)
        else:
            # STOCK, FOREX, METALS, COMMODITIES — all via MT5
            broker = factory.get(BrokerName.MT5)

        if not broker.connected:
            await broker.connect()

        trade = Trade(
            id=str(uuid.uuid4()),
            broker=broker.name,
            symbol=signal.symbol,
            asset_class=signal.asset_class,
            direction=signal.direction,
            lot_size=signal.metadata.get("lot_size", 0.01),
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            strategy=signal.strategy,
            signal_id=signal.id,
            metadata=signal.metadata,
        )

        try:
            executed_trade = await broker.place_order(trade)
            state.open_trades.append(executed_trade)
            log.success("TRADE EXECUTED: {} {} {} @ {} | SL:{} TP:{}",
                        executed_trade.direction, executed_trade.lot_size,
                        executed_trade.symbol, executed_trade.entry_price,
                        executed_trade.stop_loss, executed_trade.take_profit)
            
            # Store in Memory
            from agents.memory import memory
            context_text = f"Symbol: {signal.symbol}, Direction: {signal.direction}, Strategy: {signal.strategy}, " \
                           f"TechnicalScore: {signal.score}, MacroDXY: {state.macro_data.get('dxy_trend')}, " \
                           f"Sentiment: {signal.reasoning}"
            memory.store_trade_context(
                trade_id=executed_trade.id,
                context_text=context_text,
                metadata={
                    "symbol": signal.symbol,
                    "direction": signal.direction,
                    "strategy": signal.strategy,
                    "timestamp": str(datetime.utcnow())
                }
            )
        except Exception as e:
            log.error("⚡ ExecutionAgent: FAILED to place {} {} — {}", signal.direction, signal.symbol, e)

    state.approved_signals = []  # Clear after execution
    return state


# ═══════════════════════════════════════════════════════
#  BUILD LANGGRAPH WORKFLOW
# ═══════════════════════════════════════════════════════

def build_agent_graph():
    """
    Construct and compile the LangGraph StateGraph.
    Returns a compiled runnable graph.
    """
    if not LANGGRAPH_AVAILABLE:
        log.warning("LangGraph not installed — using sequential fallback runner")
        return None

    graph = StateGraph(BotState)

    # Register nodes
    graph.add_node("data_collector",      data_collector_node)
    graph.add_node("strategy_adapter",    strategy_adapter_node)
    graph.add_node("market_analyst",      market_analyst_node)
    graph.add_node("correlation_manager", correlation_manager_node)
    graph.add_node("sentiment_agent",     sentiment_agent_node)
    graph.add_node("calendar_agent",      calendar_agent_node)
    graph.add_node("macro_agent",         macro_agent_node)
    graph.add_node("risk_manager",        risk_manager_node)
    graph.add_node("orchestrator",        orchestrator_node)
    graph.add_node("execution_agent",     execution_agent_node)

    # Define sequential edges
    # NOTE: macro_agent runs immediately after data_collector so that
    # strategy_adapter has access to the current macro_regime (DXY / yields).
    graph.add_edge(START,                  "data_collector")
    graph.add_edge("data_collector",       "macro_agent")
    graph.add_edge("macro_agent",          "strategy_adapter")
    graph.add_edge("strategy_adapter",     "market_analyst")
    graph.add_edge("market_analyst",       "correlation_manager")
    graph.add_edge("correlation_manager",  "sentiment_agent")
    graph.add_edge("sentiment_agent",      "calendar_agent")
    graph.add_edge("calendar_agent",       "risk_manager")
    graph.add_edge("risk_manager",         "orchestrator")
    graph.add_edge("orchestrator",         "execution_agent")
    graph.add_edge("execution_agent",      END)

    return graph.compile()


# ═══════════════════════════════════════════════════════
#  SEQUENTIAL FALLBACK (if LangGraph not installed)
# ═══════════════════════════════════════════════════════

async def run_agent_pipeline(state: BotState) -> BotState:
    """Run all agents sequentially without LangGraph."""
    pipeline = [
        data_collector_node,
        macro_agent_node,              # fetch DXY/yields first so strategy_adapter has macro_regime
        strategy_adapter_node,         # regime → adapted profile + watchdog report
        market_analyst_node,
        correlation_manager_node,      # correlation / divergence checks
        sentiment_agent_node,
        calendar_agent_node,
        risk_manager_node,
        orchestrator_node,
        execution_agent_node,
    ]
    for node_fn in pipeline:
        try:
            state = await node_fn(state)
        except Exception as e:
            log.error("Agent pipeline error in {}: {}", node_fn.__name__, e)
    return state

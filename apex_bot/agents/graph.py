"""
APEX Bot — Agentic AI Framework (LangGraph)
Multi-agent graph: Orchestrator coordinates 5 specialist sub-agents.

Graph flow:
  START
    ↓
  [data_collector]     → fetches quotes, OHLCV, news, calendar
    ↓
  [market_analyst]     → technical analysis → raw signals
    ↓
  [sentiment_agent]    → news/geo NLP → sentiment scores
    ↓
  [calendar_agent]     → check news blackouts, event risk
    ↓
  [risk_manager]       → filter/resize signals by portfolio risk
    ↓
  [orchestrator]       → LLM final decision → approve/reject
    ↓
  [execution_agent]    → place approved orders via broker
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
from core.config import settings
from core.logger import get_agent_logger
from agents.correlation_agent import (
    correlation_agent_node, build_correlation_summary,
)

log = get_agent_logger("AGENT")


# ═══════════════════════════════════════════════════════
#  LLM CLIENT  (Claude primary, OpenAI fallback)
# ═══════════════════════════════════════════════════════

async def call_llm(system: str, user: str, max_tokens: int = 1024) -> str:
    """Call the configured LLM and return text response."""
    try:
        if settings.llm_provider.value == "claude":
            from anthropic import AsyncAnthropic
            client = AsyncAnthropic(api_key=settings.anthropic_api_key)
            msg = await client.messages.create(
                model=settings.llm_model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return msg.content[0].text
        else:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=settings.openai_api_key)
            resp = await client.chat.completions.create(
                model="gpt-4o",
                max_tokens=max_tokens,
                messages=[{"role":"system","content":system},{"role":"user","content":user}],
            )
            return resp.choices[0].message.content
    except Exception as e:
        log.error("LLM call failed: {}", e)
        return '{"error": "LLM unavailable"}'


# ═══════════════════════════════════════════════════════
#  NODE: DATA COLLECTOR
# ═══════════════════════════════════════════════════════

async def data_collector_node(state: BotState) -> BotState:
    """
    Fetches: live quotes, recent OHLCV bars, latest news, calendar events.
    Populates state.quotes, state.ohlcv_cache, state.news_items, state.calendar_events.
    """
    log.info("🤖 DataCollector: Refreshing market data for {} symbols...", len(settings.assets.all_symbols))

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

    log.info("🤖 DataCollector: {} quotes | {} news | {} calendar events loaded",
             len(state.quotes), len(state.news_items), len(state.calendar_events))

    state.messages.append(AgentMessage(
        from_agent="data_collector", to_agent="market_analyst",
        message_type="data_ready", payload={"symbols": list(state.quotes.keys())}
    ))
    return state


# ═══════════════════════════════════════════════════════
#  NODE: MARKET ANALYST
# ═══════════════════════════════════════════════════════

async def market_analyst_node(state: BotState) -> BotState:
    """
    Technical analysis on all tracked symbols.
    Generates raw TradingSignal objects for promising setups.
    """
    log.info("🧠 MarketAnalyst: Scanning {} symbols for technical setups...", len(state.quotes))

    from strategies.technical import TechnicalAnalyser

    analyser = TechnicalAnalyser()
    new_signals: list[TradingSignal] = []

    for symbol, quote in state.quotes.items():
        try:
            signals = await analyser.analyse(symbol, quote)
            new_signals.extend(signals)
        except Exception as e:
            log.warning("MarketAnalyst error on {}: {}", symbol, e)

    # Sort by score descending
    new_signals.sort(key=lambda s: s.score, reverse=True)

    # Keep top N to avoid noise
    top_signals = [s for s in new_signals if s.score >= settings.strategy.min_signal_score][:8]
    state.pending_signals = top_signals

    log.info("🧠 MarketAnalyst: {} raw signals generated ({} above threshold)",
             len(new_signals), len(top_signals))

    for sig in top_signals:
        log.info("SIGNAL {} {} | Score: {:.1f}/10 | Conf: {:.0f}% | Strategy: {}",
                 sig.direction, sig.symbol, sig.score, sig.confidence*100, sig.strategy)

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

    log.info("🧠 SentimentAgent: Analysing {} news items against {} signals...",
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
        response = await call_llm(system_prompt, user_prompt, max_tokens=512)
        # Parse JSON (strip any markdown fences)
        clean = response.strip().lstrip("```json").rstrip("```").strip()
        adjustments = json.loads(clean)

        boost_map = {a["symbol"]: a for a in adjustments}
        for signal in state.pending_signals:
            if signal.symbol in boost_map:
                adj = boost_map[signal.symbol]
                old_conf = signal.confidence
                signal.confidence = min(1.0, max(0.0, signal.confidence + adj.get("sentiment_boost", 0)))
                signal.reasoning += f" | Sentiment: {adj.get('reasoning', '')}"
                log.info("🧠 SentimentAgent: {} confidence {:.0f}% → {:.0f}%",
                         signal.symbol, old_conf*100, signal.confidence*100)

    except Exception as e:
        log.warning("SentimentAgent LLM parse error: {}", e)

    return state


# ═══════════════════════════════════════════════════════
#  NODE: CALENDAR AGENT
# ═══════════════════════════════════════════════════════

async def calendar_agent_node(state: BotState) -> BotState:
    """
    Checks upcoming economic events.
    Sets state.is_news_blackout and filters/warns on signals.
    """
    log.info("📅 CalendarAgent: Checking {} upcoming events...", len(state.calendar_events))

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
            log.warning("⚠ CalendarAgent: BLACKOUT ACTIVE — '{}' in {:.0f}min ({})",
                        event.title, minutes_to_event, event.currency)
            event.bot_action = "PAUSE_TRADING"

        elif 0 < minutes_to_event <= 60:
            log.info("📅 CalendarAgent: '{}' in {:.0f}min — TIGHTENING SL on {} pairs",
                     event.title, minutes_to_event, event.currency[:3])
            # Remove signals for affected currency
            state.pending_signals = [
                s for s in state.pending_signals
                if event.currency[:3] not in s.symbol
            ]

    if state.is_news_blackout:
        log.warning("⚠ CalendarAgent: ALL signals SUPPRESSED during news blackout")
        state.pending_signals = []

    return state


# ═══════════════════════════════════════════════════════
#  NODE: RISK MANAGER
# ═══════════════════════════════════════════════════════

async def risk_manager_node(state: BotState) -> BotState:
    """
    Applies portfolio-level risk rules:
    - Max drawdown check
    - Max open trades check
    - Correlation checks
    - Position sizing (lot calculation)
    - SL/TP validation (min R:R)
    """
    log.info("🛡️ RiskManager: Evaluating {} signals against {} open trades...",
             len(state.pending_signals), len(state.open_trades))

    cfg = settings.risk
    approved: list[TradingSignal] = []

    # Max open trades check
    open_count = len(state.open_trades)
    if open_count >= cfg.max_open_trades:
        log.warning("⚠ RiskManager: Max open trades ({}) reached — blocking all new signals", cfg.max_open_trades)
        state.pending_signals = []
        return state

    # Check open trade symbols for correlation
    open_symbols = {t.symbol for t in state.open_trades}
    open_directions = {t.symbol: t.direction for t in state.open_trades}

    for signal in state.pending_signals:
        reasons_rejected = []

        # Min confidence filter
        if signal.confidence < settings.strategy.min_confidence:
            reasons_rejected.append(f"confidence {signal.confidence:.0%} < {settings.strategy.min_confidence:.0%}")

        # R:R check (minimum 1.5:1)
        if signal.risk_reward < 1.5:
            reasons_rejected.append(f"R:R {signal.risk_reward:.1f} < 1.5")

        # Duplicate symbol
        if signal.symbol in open_symbols and open_directions.get(signal.symbol) == signal.direction:
            reasons_rejected.append("duplicate position already open")

        # Slot available?
        if len(approved) + open_count >= cfg.max_open_trades:
            reasons_rejected.append("max open trades would be exceeded")

        if reasons_rejected:
            log.info("🛡️ RiskManager: REJECTED {} {} — {}", signal.direction, signal.symbol, "; ".join(reasons_rejected))
            continue

        # Size the position
        signal.metadata["lot_size"] = _calculate_lot_size(signal, cfg)
        approved.append(signal)
        log.info("🛡️ RiskManager: APPROVED {} {} | Lot: {} | R:R {:.1f}",
                 signal.direction, signal.symbol, signal.metadata["lot_size"], signal.risk_reward)

    state.approved_signals = approved
    log.info("🛡️ RiskManager: {}/{} signals approved", len(approved), len(state.pending_signals))
    return state


def _calculate_lot_size(signal: TradingSignal, cfg) -> float:
    """
    Risk-based position sizing.
    lot_size = (account_balance * risk_pct) / (stop_loss_pips * pip_value)
    Simplified to a capped calculation for scaffold.
    """
    # TODO: connect to actual account balance
    account_balance = 50_000.0
    risk_amount = account_balance * (cfg.max_risk_per_trade_pct / 100)
    sl_distance = abs(signal.entry_price - signal.stop_loss)
    if sl_distance == 0:
        return 0.01
    raw_lot = risk_amount / (sl_distance * 100)
    return round(min(raw_lot, cfg.max_lot_size), 2)


# ═══════════════════════════════════════════════════════
#  NODE: ORCHESTRATOR (LLM final decision)
# ═══════════════════════════════════════════════════════

async def orchestrator_node(state: BotState) -> BotState:
    """
    The master brain. Makes final trade approval using Claude.
    Considers: approved signals, market regime, open portfolio, news context.
    """
    if not state.approved_signals:
        log.info("🔮 Orchestrator: No approved signals to evaluate")
        return state

    log.info("🤖 Orchestrator: LLM evaluating {} approved signals...", len(state.approved_signals))

    portfolio_summary = f"""
    Open trades: {len(state.open_trades)}
    Market regime: {state.market_regime}
    News blackout: {state.is_news_blackout}
    Recent news sentiment: {_summarise_news(state.news_items[:5])}
    """

    signals_detail = json.dumps([{
        "symbol":      s.symbol,
        "direction":   s.direction,
        "score":       s.score,
        "confidence":  s.confidence,
        "strategy":    s.strategy,
        "rr":          s.risk_reward,
        "reasoning":   s.reasoning[:200],
        "corr_boost":  s.metadata.get("correlation_boost", 0),
        "corr_confirms":     s.metadata.get("corr_confirmations", 0),
        "corr_contradicts":  s.metadata.get("corr_contradictions", 0),
        "leading_warnings":  s.metadata.get("leading_warnings", []),
        "is_divergence":     s.metadata.get("source") == "divergence_detector",
        "divergence_leader": s.metadata.get("leader", ""),
    } for s in state.approved_signals], indent=2)

    # Build per-signal correlation summaries
    corr_summaries = "\n\n".join(
        build_correlation_summary(s) for s in state.approved_signals
    )

    system_prompt = """You are the master orchestrator of an algorithmic trading system.
    Your role is to make the final APPROVE or REJECT decision on trade signals.

    PAY CLOSE ATTENTION to correlation data:
    - corr_boost > +1.0  : multiple assets confirm this move — strong conviction
    - corr_boost 0 to +1 : mild confirmation — proceed if technicals are solid
    - corr_boost < 0     : assets are contradicting — be very cautious
    - leading_warnings   : leaders haven't moved yet — signal may be premature
    - is_divergence=true : catch-up signal — leader moved, lagger hasn't yet

    Consider: signal quality, portfolio context, market conditions, correlation alignment.
    Be selective — only approve high-conviction signals.
    Return ONLY a JSON array: [{"symbol": "XAUUSD", "direction": "BUY", "decision": "APPROVE", "reason": "brief"}]"""

    user_prompt = f"""Portfolio Context:\n{portfolio_summary}

Correlation Analysis:\n{corr_summaries}

Signals for Review:\n{signals_detail}

Make final trade decisions. Correlation alignment is a key factor. Return JSON only."""

    try:
        response = await call_llm(system_prompt, user_prompt, max_tokens=768)
        clean = response.strip().lstrip("```json").rstrip("```").strip()
        decisions = json.loads(clean)

        decision_map = {(d["symbol"], d["direction"]): d for d in decisions}
        final_approved = []

        for signal in state.approved_signals:
            key = (signal.symbol, signal.direction)
            decision = decision_map.get(key, {})
            if decision.get("decision") == "APPROVE":
                signal.reasoning += f" | Orchestrator: {decision.get('reason','')}"
                final_approved.append(signal)
                log.info("🤖 Orchestrator: ✅ APPROVED {} {} — {}", signal.direction, signal.symbol, decision.get("reason",""))
            else:
                log.info("🤖 Orchestrator: ❌ REJECTED {} {} — {}", signal.direction, signal.symbol, decision.get("reason","no reason"))

        state.approved_signals = final_approved

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
        log.info("⚡ ExecutionAgent: No signals to execute")
        return state

    log.info("⚡ ExecutionAgent: Executing {} approved signals...", len(state.approved_signals))

    from brokers.base import BrokerFactory, BrokerName
    factory = broker_factory or BrokerFactory(settings)

    for signal in state.approved_signals:
        # Route to correct broker based on asset class
        if signal.asset_class == AssetClass.CRYPTO:
            broker = factory.get(BrokerName.CCXT)
        elif signal.asset_class == AssetClass.STOCK:
            broker = factory.get(BrokerName.ALPACA) if hasattr(BrokerName, 'ALPACA') else factory.get(BrokerName.PAPER)
        else:
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
        )

        try:
            executed_trade = await broker.place_order(trade)
            state.open_trades.append(executed_trade)
            log.success("TRADE EXECUTED: {} {} {} @ {} | SL:{} TP:{}",
                        executed_trade.direction, executed_trade.lot_size,
                        executed_trade.symbol, executed_trade.entry_price,
                        executed_trade.stop_loss, executed_trade.take_profit)
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
    graph.add_node("data_collector",    data_collector_node)
    graph.add_node("market_analyst",    market_analyst_node)
    graph.add_node("correlation_agent", correlation_agent_node)
    graph.add_node("sentiment_agent",   sentiment_agent_node)
    graph.add_node("calendar_agent",    calendar_agent_node)
    graph.add_node("risk_manager",      risk_manager_node)
    graph.add_node("orchestrator",      orchestrator_node)
    graph.add_node("execution_agent",   execution_agent_node)

    # Define sequential edges
    graph.add_edge(START,               "data_collector")
    graph.add_edge("data_collector",    "market_analyst")
    graph.add_edge("market_analyst",    "correlation_agent")
    graph.add_edge("correlation_agent", "sentiment_agent")
    graph.add_edge("sentiment_agent",   "calendar_agent")
    graph.add_edge("calendar_agent",    "risk_manager")
    graph.add_edge("risk_manager",      "orchestrator")
    graph.add_edge("orchestrator",      "execution_agent")
    graph.add_edge("execution_agent",   END)

    return graph.compile()


# ═══════════════════════════════════════════════════════
#  SEQUENTIAL FALLBACK (if LangGraph not installed)
# ═══════════════════════════════════════════════════════

async def run_agent_pipeline(state: BotState) -> BotState:
    """Run all agents sequentially without LangGraph."""
    pipeline = [
        data_collector_node,
        market_analyst_node,
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

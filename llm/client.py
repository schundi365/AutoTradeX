"""
APEX Bot — Tiered LLM Client
Fallback chain: Local Ollama (fine-tuned) → Groq → DeepSeek → Claude Haiku
Rules:
  - NEVER let an LLM failure crash the pipeline
  - asyncio.wait_for() for per-tier timeouts (not httpx timeout alone)
  - Return None if all tiers fail; callers must handle None gracefully
  - Log which tier was used for every call
  - Handle rate limits with exponential backoff
"""
from __future__ import annotations
import asyncio
import json
import time
from typing import Optional

import httpx
from loguru import logger as log

from core.config import settings


# ── Tier timeouts ────────────────────────────────────────────────────────────
OLLAMA_TIMEOUT   = float(getattr(settings, "llm_timeout_seconds", 5))  # local is fast or down
GROQ_TIMEOUT     = 10.0
DEEPSEEK_TIMEOUT = 12.0
CLAUDE_TIMEOUT   = 15.0

# ── Rate limit tracking ──────────────────────────────────────────────────────
_rate_limit_cache = {}  # tier -> (reset_time, retry_after)


# ── Database logging helper ──────────────────────────────────────────────────
async def _log_llm_call(agent: str, tier: str, model: str, latency_ms: int, 
                        success: bool, timeout: bool, error: bool):
    """Log LLM call to database for health monitoring."""
    try:
        from datetime import datetime
        from memory.duckdb_store import DuckDBStore
        
        store = DuckDBStore(settings.training.duckdb_path)
        await store.start()
        
        await store.execute_write("""
            INSERT INTO llm_calls 
            (timestamp, agent, tier, model, latency_ms, success, timeout, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [datetime.utcnow(), agent, tier, model, latency_ms, 
              1 if success else 0, 1 if timeout else 0, 1 if error else 0])
        
        await store.stop()
    except Exception as e:
        # Don't fail the LLM call if logging fails
        log.debug("Failed to log LLM call: {}", e)


# ─────────────────────────────────────────────────────────────────────────────
#  TIER 1 — Local Ollama
# ─────────────────────────────────────────────────────────────────────────────
async def _call_ollama(system: str, user: str, max_tokens: int) -> Optional[str]:
    prompt = f"{system}\n\n{user}"
    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": max_tokens},
    }
    async with httpx.AsyncClient() as client:
        resp = await asyncio.wait_for(
            client.post(f"{settings.ollama_base_url}/api/generate", json=payload),
            timeout=OLLAMA_TIMEOUT,
        )
    if resp.status_code == 200:
        return resp.json().get("response", "").strip()
    return None


# ─────────────────────────────────────────────────────────────────────────────
#  TIER 2 — Groq (Fast inference with rate limits)
# ─────────────────────────────────────────────────────────────────────────────
def _is_rate_limited(tier: str) -> bool:
    """Check if a tier is currently rate limited."""
    if tier not in _rate_limit_cache:
        return False
    reset_time, _ = _rate_limit_cache[tier]
    if time.time() < reset_time:
        return True
    # Rate limit expired, clear it
    del _rate_limit_cache[tier]
    return False


def _set_rate_limit(tier: str, retry_after: float):
    """Mark a tier as rate limited."""
    reset_time = time.time() + retry_after
    _rate_limit_cache[tier] = (reset_time, retry_after)
    log.warning(f"[{tier}] Rate limited for {retry_after:.1f}s")


async def _call_groq(system: str, user: str, max_tokens: int) -> Optional[str]:
    """Call Groq API with rate limit handling."""
    if _is_rate_limited("groq"):
        reset_time, retry_after = _rate_limit_cache["groq"]
        remaining = reset_time - time.time()
        log.debug(f"[Groq] Still rate limited, {remaining:.1f}s remaining")
        return None
    
    try:
        from openai import AsyncOpenAI
        
        client = AsyncOpenAI(
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        )
        
        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=getattr(settings, "groq_model", "llama-3.3-70b-versatile"),
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    max_tokens=max_tokens,
                    temperature=0.1,
                ),
                timeout=GROQ_TIMEOUT,
            )
            return response.choices[0].message.content.strip()
        finally:
            await client.close()
        
    except Exception as e:
        error_str = str(e)
        # Check for rate limit error
        if "rate_limit" in error_str.lower() or "429" in error_str:
            # Try to extract retry_after from error message
            retry_after = 150  # Default 2.5 minutes
            if "try again in" in error_str.lower():
                # Parse "try again in 2m25.152s"
                import re
                match = re.search(r'(\d+)m(\d+(?:\.\d+)?)s', error_str)
                if match:
                    minutes = int(match.group(1))
                    seconds = float(match.group(2))
                    retry_after = minutes * 60 + seconds
            _set_rate_limit("groq", retry_after)
        raise


# ─────────────────────────────────────────────────────────────────────────────
#  TIER 3 — DeepSeek (OpenAI-compatible API)
# ─────────────────────────────────────────────────────────────────────────────
async def _call_deepseek(system: str, user: str, max_tokens: int) -> Optional[str]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url="https://api.deepseek.com",
    )
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                temperature=0.1,
            ),
            timeout=DEEPSEEK_TIMEOUT,
        )
        return response.choices[0].message.content.strip()
    finally:
        await client.close()


# ─────────────────────────────────────────────────────────────────────────────
#  TIER 4 — Claude Haiku (Anthropic)
# ─────────────────────────────────────────────────────────────────────────────
async def _call_claude(system: str, user: str, max_tokens: int) -> Optional[str]:
    try:
        from anthropic import AsyncAnthropic
    except ImportError as e:
        log.warning("Anthropic library not available: {}", e)
        return None

    try:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    except TypeError as e:
        # Handle version incompatibility (e.g., proxies parameter not supported)
        log.warning("Anthropic client initialization failed (version incompatibility?): {}", e)
        return None
    
    try:
        msg = await asyncio.wait_for(
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            ),
            timeout=CLAUDE_TIMEOUT,
        )
        return msg.content[0].text.strip()
    finally:
        try:
            await client.close()
        except Exception:
            pass  # Ignore close errors


# ─────────────────────────────────────────────────────────────────────────────
#  TIER RACING — Groq + DeepSeek in parallel (fastest wins)
# ─────────────────────────────────────────────────────────────────────────────
async def _race_cloud_tiers(
    system: str, user: str, max_tokens: int, agent: str
) -> tuple[Optional[str], str]:
    """
    Fire Groq and DeepSeek simultaneously; return (result, tier_name) for
    whichever answers first with a non-empty string.  Returns ("", "") if both fail.
    Groq is skipped if it is currently rate-limited.
    """
    coros: dict[str, asyncio.coroutines] = {}
    if getattr(settings, "groq_api_key", None) and not _is_rate_limited("groq"):
        coros["groq"] = asyncio.wait_for(_call_groq(system, user, max_tokens), timeout=GROQ_TIMEOUT)
    if getattr(settings, "deepseek_api_key", None):
        coros["deepseek"] = asyncio.wait_for(_call_deepseek(system, user, max_tokens), timeout=DEEPSEEK_TIMEOUT)

    if not coros:
        return None, ""

    tasks: dict[str, asyncio.Task] = {
        name: asyncio.ensure_future(coro) for name, coro in coros.items()
    }
    pending = set(tasks.values())

    winner_result: Optional[str] = None
    winner_name: str = ""

    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            name = next(k for k, v in tasks.items() if v is t)
            try:
                result = t.result()
                if result:
                    winner_result = result
                    winner_name = name
                    # Cancel the slower sibling
                    for remaining in pending:
                        remaining.cancel()
                    pending.clear()
                    break
            except asyncio.TimeoutError:
                log.warning("[{}] {} timed out in tier race", agent, name)
            except Exception as e:
                err = str(e)
                if "rate_limit" in err.lower() or "429" in err:
                    _set_rate_limit("groq", 150)
                log.warning("[{}] {} failed in tier race: {}", agent, name, e)

    # Cleanly await any cancelled tasks to avoid event-loop warnings
    if pending:
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    return winner_result, winner_name


# ─────────────────────────────────────────────────────────────────────────────
#  PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────────────────────────
async def call_llm(
    system: str,
    user: str,
    max_tokens: int = 1024,
    agent: str = "unknown",
) -> Optional[str]:
    """
    Tiered LLM call. Returns the response string or None if all tiers fail.
    Callers must handle None — never crash on a missing LLM response.
    """
    start_time = time.time()

    def _log_async(tier: str, model: str, success: bool, timed_out: bool, errored: bool):
        """Fire-and-forget DB log — never blocks the LLM response path."""
        latency_ms = int((time.time() - start_time) * 1000)
        try:
            asyncio.ensure_future(
                _log_llm_call(agent, tier, model, latency_ms, success, timed_out, errored)
            )
        except RuntimeError:
            pass  # No running loop (rare edge-case during shutdown)

    # ── Tier 1: Ollama (local, fastest if available) ─────────────────────────
    if getattr(settings, "ollama_base_url", None):
        try:
            result = await _call_ollama(system, user, max_tokens)
            if result:
                log.info("[{}] 🤖 LLM Tier 1 (Ollama/{}) ✓", agent, settings.ollama_model)
                _log_async("ollama", settings.ollama_model, True, False, False)
                return result
        except asyncio.TimeoutError:
            _log_async("ollama", settings.ollama_model, False, True, False)
            log.warning("[{}] Ollama timeout ({}s) → racing cloud tiers", agent, OLLAMA_TIMEOUT)
        except Exception as e:
            _log_async("ollama", settings.ollama_model, False, False, True)
            log.warning("[{}] Ollama unavailable ({}) → racing cloud tiers", agent, e)

    # ── Tier 2+3: Groq ∥ DeepSeek (fastest wins) ─────────────────────────────
    has_groq     = bool(getattr(settings, "groq_api_key", None))
    has_deepseek = bool(getattr(settings, "deepseek_api_key", None))

    if has_groq or has_deepseek:
        try:
            result, tier_name = await _race_cloud_tiers(system, user, max_tokens, agent)
            if result:
                model_name = "llama-3.3-70b" if tier_name == "groq" else "deepseek-chat"
                log.info("[{}] 🤖 LLM {} (cloud race) ✓", agent, tier_name)
                _log_async(tier_name, model_name, True, False, False)
                return result
            else:
                log.warning("[{}] Cloud tier race returned nothing → falling back to Claude", agent)
        except Exception as e:
            log.warning("[{}] Cloud tier race exception: {} → falling back to Claude", agent, e)

    # ── Tier 4: Claude Haiku (final fallback) ────────────────────────────────
    if getattr(settings, "anthropic_api_key", None):
        try:
            result = await _call_claude(system, user, max_tokens)
            if result:
                log.info("[{}] 🤖 LLM Tier 4 (Claude Haiku) ✓", agent)
                _log_async("claude", "claude-haiku-4-5", True, False, False)
                return result
        except asyncio.TimeoutError:
            _log_async("claude", "claude-haiku-4-5", False, True, False)
            log.error("[{}] Claude timeout ({}s) — all LLM tiers exhausted", agent, CLAUDE_TIMEOUT)
        except Exception as e:
            _log_async("claude", "claude-haiku-4-5", False, False, True)
            log.error("[{}] Claude failed ({}) — all LLM tiers exhausted", agent, e)

    log.error("[{}] ⚠ All LLM tiers failed — caller must use fallback logic", agent)
    return None


def parse_llm_json(response: Optional[str], fallback: dict) -> dict:
    """
    Safely extract a JSON block from an LLM response.
    Returns fallback dict if parsing fails or response is None.
    """
    if not response:
        return fallback
    try:
        # Try to find JSON block in the response
        start = response.find("{")
        end = response.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(response[start:end])
    except Exception:
        pass
    return fallback


class LLMClient:
    """
    Convenience wrapper for agents that prefer an object-oriented interface.
    Usage: client = LLMClient(agent_name="market_analyst")
           result = await client.generate(system=..., user=...)
    """

    def __init__(self, agent_name: str = "agent"):
        self.agent_name = agent_name

    async def generate(
        self,
        system: str,
        user: str,
        max_tokens: int = 1024,
    ) -> Optional[str]:
        return await call_llm(system, user, max_tokens, agent=self.agent_name)

    async def generate_json(
        self,
        system: str,
        user: str,
        max_tokens: int = 1024,
        fallback: Optional[dict] = None,
    ) -> dict:
        raw = await self.generate(system, user, max_tokens)
        return parse_llm_json(raw, fallback or {})

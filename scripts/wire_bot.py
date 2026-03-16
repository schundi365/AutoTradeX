"""
APEX Bot — wire_bot.py
Integration reference: how to wire the tiered LLM client into agents.
This is the COMPLETE implementation — import llm/client.py from your agents.

The full tiered client lives in llm/client.py.
This file is a quick-start integration reference + standalone test runner.

Usage:
  python scripts/wire_bot.py                        # test all 3 tiers
  python scripts/wire_bot.py --tier ollama          # test Ollama only
  python scripts/wire_bot.py --tier deepseek
  python scripts/wire_bot.py --tier claude
  python scripts/wire_bot.py --prompt "XAUUSD BUY setup: RSI=58, ADX=31, DXY=-0.3%"
"""
from __future__ import annotations
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import settings

# ─────────────────────────────────────────────────────────────────────────────
# Standalone tiered LLM call (mirrors llm/client.py exactly)
# ─────────────────────────────────────────────────────────────────────────────

APEX_SYSTEM_PROMPT = """\
You are APEX, an expert algorithmic trading analyst specializing in:
- Gold (XAUUSD) using Smart Money Concepts
- Macro analysis via DXY and US Treasury yields
- Multi-timeframe technical analysis

Your decisions must include:
1. DECISION: APPROVE or REJECT
2. CONFIDENCE: 0.00–1.00
3. Numbered REASONING (trend, momentum, macro, sentiment, calendar)
4. ENTRY, STOP_LOSS, TAKE_PROFIT, RISK_REWARD (for approved trades)

You are conservative — prefer NO TRADE over a low-quality setup.
Always respect macro vetoes and news blackout windows.
"""


async def _tier1_ollama(system: str, user: str, max_tokens: int = 512) -> str | None:
    """Tier 1: Local Ollama (fine-tuned apex-trader model)."""
    try:
        import httpx
        payload = {
            "model": settings.ollama_model,
            "prompt": f"{system}\n\n{user}",
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": max_tokens},
        }
        async with httpx.AsyncClient() as client:
            resp = await asyncio.wait_for(
                client.post(f"{settings.ollama_base_url}/api/generate", json=payload),
                timeout=8.0,
            )
        if resp.status_code == 200:
            return resp.json().get("response", "").strip()
    except asyncio.TimeoutError:
        print("  Ollama: timeout (8s)")
    except Exception as e:
        print(f"  Ollama: unavailable ({e})")
    return None


async def _tier2_deepseek(system: str, user: str, max_tokens: int = 512) -> str | None:
    """Tier 2: DeepSeek API (OpenAI-compatible endpoint)."""
    if not settings.deepseek_api_key:
        print("  DeepSeek: no API key configured (DEEPSEEK_API_KEY)")
        return None
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url="https://api.deepseek.com",
        )
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                temperature=0.1,
            ),
            timeout=12.0,
        )
        return resp.choices[0].message.content.strip()
    except asyncio.TimeoutError:
        print("  DeepSeek: timeout (12s)")
    except Exception as e:
        print(f"  DeepSeek: failed ({e})")
    return None


async def _tier3_claude(system: str, user: str, max_tokens: int = 512) -> str | None:
    """Tier 3: Claude Haiku via Anthropic SDK."""
    if not settings.anthropic_api_key:
        print("  Claude: no API key configured (ANTHROPIC_API_KEY)")
        return None
    try:
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        msg = await asyncio.wait_for(
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            ),
            timeout=15.0,
        )
        return msg.content[0].text.strip()
    except asyncio.TimeoutError:
        print("  Claude: timeout (15s)")
    except Exception as e:
        print(f"  Claude: failed ({e})")
    return None


async def call_llm_tiered(
    system: str,
    user: str,
    max_tokens: int = 512,
    tier_only: str | None = None,
) -> str | None:
    """
    Full tiered fallback call. Used in agents via llm/client.py.
    tier_only: "ollama" | "deepseek" | "claude" for testing a specific tier.
    """
    if tier_only in (None, "ollama"):
        result = await _tier1_ollama(system, user, max_tokens)
        if result:
            print("  [Tier 1 - Ollama] ✓")
            return result
        if tier_only == "ollama":
            return None

    if tier_only in (None, "deepseek"):
        result = await _tier2_deepseek(system, user, max_tokens)
        if result:
            print("  [Tier 2 - DeepSeek] ✓")
            return result
        if tier_only == "deepseek":
            return None

    if tier_only in (None, "claude"):
        result = await _tier3_claude(system, user, max_tokens)
        if result:
            print("  [Tier 3 - Claude Haiku] ✓")
            return result

    # All tiers failed — fallback logic for agents
    print("  ⚠ All LLM tiers failed — caller should use score-based fallback")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Integration snippet: how agents call the LLM
# ─────────────────────────────────────────────────────────────────────────────

AGENT_INTEGRATION_EXAMPLE = '''
# In any agent (e.g. agents/orchestrator.py):

from llm.client import call_llm, parse_llm_json

async def orchestrator_node(state: BotState) -> BotState:
    for signal in state.approved_signals:
        system = "You are APEX trading analyst..."
        user = f"Symbol: {signal.symbol} | Score: {signal.score} | ..."

        raw = await call_llm(system, user, max_tokens=512, agent="orchestrator")

        # Parse structured JSON from response
        parsed = parse_llm_json(raw, fallback={"decision": "REJECT", "reason": "LLM failed"})
        decision = parsed.get("decision", "REJECT")

        # Fallback when ALL tiers fail: approve only high-confidence signals
        if raw is None:
            decision = "APPROVE" if signal.score > 8.0 else "REJECT"
            log.warning("LLM fallback: score-based decision for {}", signal.symbol)
'''

# ─────────────────────────────────────────────────────────────────────────────
# Test runner
# ─────────────────────────────────────────────────────────────────────────────

async def run_test(prompt: str, tier: str | None = None):
    test_user = prompt or (
        "Symbol: XAUUSD | Direction: BUY | Score: 8.2 | Confidence: 0.82\n"
        "RSI: 58.2 | ADX: 31.2 | ATR%: 0.36\n"
        "Macro: DXY=-0.30% | US10Y=-4bps | Regime: RISK_ON\n"
        "News: Fed holds, USD softening | Sentiment: +0.60\n"
        "Calendar: No events in next 4 hours\n"
        "\nMake a structured trading decision."
    )

    print(f"\n{'='*60}")
    print(f"Testing LLM tier: {'ALL (fallback chain)' if not tier else tier.upper()}")
    print(f"{'='*60}\n")
    print(f"Prompt:\n{test_user}\n")
    print("-"*60)

    result = await call_llm_tiered(
        system=APEX_SYSTEM_PROMPT,
        user=test_user,
        max_tokens=512,
        tier_only=tier,
    )

    if result:
        print(f"\nResponse:\n{result}")
    else:
        print("\nNo response — all requested tiers unavailable")
        print("\nFallback logic: approve signals with score > 8.0, reject the rest")

    print(f"\n{'='*60}")
    print("Integration: in agents, use  from llm.client import call_llm")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="APEX LLM tier tester")
    parser.add_argument(
        "--tier",
        choices=["ollama", "deepseek", "claude"],
        default=None,
        help="Test a specific tier only (default: full fallback chain)",
    )
    parser.add_argument(
        "--prompt", default=None,
        help="Custom prompt to test with"
    )
    parser.add_argument(
        "--show-integration", action="store_true",
        help="Print the agent integration code example"
    )
    args = parser.parse_args()

    if args.show_integration:
        print(AGENT_INTEGRATION_EXAMPLE)
        return

    print(f"\nOllama   : {settings.ollama_base_url} / model={settings.ollama_model}")
    print(f"DeepSeek : {'configured' if settings.deepseek_api_key else 'NO KEY'}")
    print(f"Claude   : {'configured' if settings.anthropic_api_key else 'NO KEY'}")

    asyncio.run(run_test(args.prompt, tier=args.tier))


if __name__ == "__main__":
    main()

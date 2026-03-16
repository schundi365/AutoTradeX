"""
APEX Health API Endpoints
Provides real-time health monitoring, tier breakdown, and control actions
"""
from __future__ import annotations
import asyncio
import subprocess
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger as log

from core.config import settings
from llm.client import call_llm


router = APIRouter(prefix="/api/apex", tags=["apex-health"])


# ═══════════════════════════════════════════════════════
#  MODELS
# ═══════════════════════════════════════════════════════
class TierBreakdownResponse(BaseModel):
    tiers: list[dict]
    total_calls: int
    time_range: str


class TestTiersResponse(BaseModel):
    success: bool
    tiers_tested: int
    tiers_passed: int
    results: list[dict]
    message: str


class RestartOllamaResponse(BaseModel):
    success: bool
    message: str


# ═══════════════════════════════════════════════════════
#  ENDPOINTS
# ═══════════════════════════════════════════════════════
@router.get("/health/tier-breakdown")
async def get_tier_breakdown() -> TierBreakdownResponse:
    """
    Get LLM tier usage breakdown for the last 24 hours.
    Returns call count and average latency per tier.
    """
    try:
        from memory.duckdb_store import DuckDBStore
        
        store = DuckDBStore(settings.training.duckdb_path)
        await store.start()
        
        # Query tier stats from last 24 hours
        query = """
            SELECT 
                tier,
                COUNT(*) as calls,
                AVG(latency_ms) as avg_latency_ms,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as success_rate
            FROM llm_calls
            WHERE timestamp >= datetime('now', '-24 hours')
            GROUP BY tier
            ORDER BY calls DESC
        """
        
        rows = await store.execute_read(query)
        await store.stop()
        
        tiers = []
        total_calls = 0
        
        for row in rows:
            tier_data = {
                "name": row[0].capitalize(),
                "calls": row[1],
                "avg_latency_ms": round(row[2], 1) if row[2] else 0,
                "success_rate": round(row[3], 1) if row[3] else 0
            }
            tiers.append(tier_data)
            total_calls += row[1]
        
        # If no data, return mock data
        if not tiers:
            tiers = [
                {"name": "Ollama", "calls": 0, "avg_latency_ms": 0, "success_rate": 0},
                {"name": "Groq", "calls": 0, "avg_latency_ms": 0, "success_rate": 0},
                {"name": "DeepSeek", "calls": 0, "avg_latency_ms": 0, "success_rate": 0},
                {"name": "Claude", "calls": 0, "avg_latency_ms": 0, "success_rate": 0}
            ]
        
        return TierBreakdownResponse(
            tiers=tiers,
            total_calls=total_calls,
            time_range="24h"
        )
        
    except Exception as e:
        log.error(f"[APEX Health] Tier breakdown error: {e}")
        # Return empty data on error
        return TierBreakdownResponse(
            tiers=[
                {"name": "Ollama", "calls": 0, "avg_latency_ms": 0, "success_rate": 0},
                {"name": "Groq", "calls": 0, "avg_latency_ms": 0, "success_rate": 0},
                {"name": "DeepSeek", "calls": 0, "avg_latency_ms": 0, "success_rate": 0},
                {"name": "Claude", "calls": 0, "avg_latency_ms": 0, "success_rate": 0}
            ],
            total_calls=0,
            time_range="24h"
        )


@router.post("/test-tiers")
async def test_llm_tiers() -> TestTiersResponse:
    """
    Test all LLM tiers with a simple prompt to verify connectivity.
    Returns success/failure status for each tier.
    """
    test_prompt_system = "You are a helpful assistant. Respond with exactly: OK"
    test_prompt_user = "Test"
    
    results = []
    tiers_tested = 0
    tiers_passed = 0
    
    # Test Ollama
    if settings.ollama_base_url:
        tiers_tested += 1
        try:
            from llm.client import _call_ollama
            result = await _call_ollama(test_prompt_system, test_prompt_user, 10)
            if result:
                results.append({"tier": "Ollama", "status": "✅ PASS", "latency_ms": 0, "response": result[:50]})
                tiers_passed += 1
            else:
                results.append({"tier": "Ollama", "status": "❌ FAIL", "error": "No response"})
        except Exception as e:
            results.append({"tier": "Ollama", "status": "❌ FAIL", "error": str(e)[:100]})
    
    # Test Groq
    if getattr(settings, "groq_api_key", None):
        tiers_tested += 1
        try:
            from llm.client import _call_groq
            result = await _call_groq(test_prompt_system, test_prompt_user, 10)
            if result:
                results.append({"tier": "Groq", "status": "✅ PASS", "latency_ms": 0, "response": result[:50]})
                tiers_passed += 1
            else:
                results.append({"tier": "Groq", "status": "❌ FAIL", "error": "No response"})
        except Exception as e:
            results.append({"tier": "Groq", "status": "❌ FAIL", "error": str(e)[:100]})
    
    # Test DeepSeek
    if settings.deepseek_api_key:
        tiers_tested += 1
        try:
            from llm.client import _call_deepseek
            result = await _call_deepseek(test_prompt_system, test_prompt_user, 10)
            if result:
                results.append({"tier": "DeepSeek", "status": "✅ PASS", "latency_ms": 0, "response": result[:50]})
                tiers_passed += 1
            else:
                results.append({"tier": "DeepSeek", "status": "❌ FAIL", "error": "No response"})
        except Exception as e:
            results.append({"tier": "DeepSeek", "status": "❌ FAIL", "error": str(e)[:100]})
    
    # Test Claude
    if settings.anthropic_api_key:
        tiers_tested += 1
        try:
            from llm.client import _call_claude
            result = await _call_claude(test_prompt_system, test_prompt_user, 10)
            if result:
                results.append({"tier": "Claude", "status": "✅ PASS", "latency_ms": 0, "response": result[:50]})
                tiers_passed += 1
            else:
                results.append({"tier": "Claude", "status": "❌ FAIL", "error": "No response"})
        except Exception as e:
            results.append({"tier": "Claude", "status": "❌ FAIL", "error": str(e)[:100]})
    
    success = tiers_passed > 0
    message = f"Tested {tiers_tested} tiers - {tiers_passed} passed, {tiers_tested - tiers_passed} failed"
    
    log.info(f"[APEX Health] Tier test complete: {message}")
    
    return TestTiersResponse(
        success=success,
        tiers_tested=tiers_tested,
        tiers_passed=tiers_passed,
        results=results,
        message=message
    )


@router.post("/restart-ollama")
async def restart_ollama() -> RestartOllamaResponse:
    """
    Restart the Ollama service (Windows only).
    Uses PowerShell to stop and start the Ollama process.
    """
    try:
        import platform
        
        if platform.system() != "Windows":
            return RestartOllamaResponse(
                success=False,
                message="Ollama restart is only supported on Windows"
            )
        
        log.info("[APEX Health] Restarting Ollama service...")
        
        # Stop Ollama
        try:
            subprocess.run(
                ["powershell", "-Command", "Stop-Process -Name 'ollama' -Force -ErrorAction SilentlyContinue"],
                check=False,
                capture_output=True,
                timeout=5
            )
            await asyncio.sleep(2)
        except Exception as e:
            log.warning(f"[APEX Health] Error stopping Ollama: {e}")
        
        # Start Ollama
        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )
            await asyncio.sleep(3)
        except Exception as e:
            log.error(f"[APEX Health] Error starting Ollama: {e}")
            return RestartOllamaResponse(
                success=False,
                message=f"Failed to start Ollama: {str(e)}"
            )
        
        # Verify Ollama is running
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{settings.ollama_base_url}/api/tags", timeout=5.0)
                if resp.status_code == 200:
                    log.info("[APEX Health] Ollama restarted successfully")
                    return RestartOllamaResponse(
                        success=True,
                        message="Ollama service restarted successfully"
                    )
        except Exception as e:
            log.warning(f"[APEX Health] Ollama verification failed: {e}")
        
        return RestartOllamaResponse(
            success=False,
            message="Ollama started but verification failed - check if service is running"
        )
        
    except Exception as e:
        log.error(f"[APEX Health] Restart error: {e}")
        return RestartOllamaResponse(
            success=False,
            message=f"Restart failed: {str(e)}"
        )


@router.get("/health/alerts")
async def get_health_alerts():
    """
    Get recent health alerts based on LLM performance.
    Returns alerts for offline status, high latency, low success rate, etc.
    """
    alerts = []
    
    try:
        from memory.duckdb_store import DuckDBStore
        
        store = DuckDBStore(settings.training.duckdb_path)
        await store.start()
        
        # Check for recent failures
        query = """
            SELECT 
                tier,
                COUNT(*) as total,
                SUM(CASE WHEN error = 1 THEN 1 ELSE 0 END) as errors,
                AVG(latency_ms) as avg_latency
            FROM llm_calls
            WHERE timestamp >= datetime('now', '-1 hour')
            GROUP BY tier
        """
        
        rows = await store.execute_read(query)
        await store.stop()
        
        for row in rows:
            tier, total, errors, avg_latency = row
            error_rate = (errors / total * 100) if total > 0 else 0
            
            # High error rate alert
            if error_rate > 20:
                alerts.append({
                    "type": "error",
                    "title": f"{tier.capitalize()} High Error Rate",
                    "message": f"{error_rate:.1f}% of calls failed in the last hour",
                    "timestamp": datetime.utcnow().isoformat()
                })
            
            # High latency alert
            if avg_latency and avg_latency > 3000:
                alerts.append({
                    "type": "warning",
                    "title": f"{tier.capitalize()} High Latency",
                    "message": f"Average latency is {avg_latency:.0f}ms (threshold: 3000ms)",
                    "timestamp": datetime.utcnow().isoformat()
                })
        
    except Exception as e:
        log.error(f"[APEX Health] Alerts error: {e}")
    
    return {"alerts": alerts}

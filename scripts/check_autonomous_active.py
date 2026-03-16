"""
Check if the bot is using the new autonomous logic.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from loguru import logger as log


async def check_autonomous_status():
    """Check if autonomous orchestrator is active"""
    log.info("=" * 60)
    log.info("CHECKING AUTONOMOUS SYSTEM STATUS")
    log.info("=" * 60)
    
    try:
        async with httpx.AsyncClient() as client:
            # Check bot status
            resp = await client.get("http://localhost:8000/api/status", timeout=5.0)
            if resp.status_code != 200:
                log.error("✗ API server not responding properly")
                return False
            
            status = resp.json()
            bot_running = status.get('bot_running', False)
            
            log.info(f"\n1. Bot Status:")
            log.info(f"   Running: {bot_running}")
            log.info(f"   Open Trades: {status.get('open_trades', 0)}")
            
            if not bot_running:
                log.warning("\n⚠️  Bot is not running!")
                log.info("   Start the bot to see autonomous system in action")
                return False
            
            # Check autonomous stats
            log.info(f"\n2. Checking Autonomous System...")
            resp = await client.get("http://localhost:8000/api/autonomous/stats", timeout=5.0)
            
            if resp.status_code != 200:
                log.error("✗ Autonomous stats endpoint not responding")
                return False
            
            stats = resp.json()
            
            if not stats.get('enabled', False):
                log.warning("✗ Autonomous system is NOT enabled")
                log.info(f"   Message: {stats.get('message', 'Unknown')}")
                return False
            
            log.info("✓ Autonomous system is ENABLED")
            
            # Show performance stats
            perf = stats.get('performance', {})
            log.info(f"\n3. Performance Metrics:")
            log.info(f"   Total Decisions: {perf.get('total_decisions', 0)}")
            log.info(f"   Fast Path %: {perf.get('fast_path_percentage', 0):.1f}%")
            log.info(f"   LLM Decisions: {perf.get('llm_decisions', 0)}")
            log.info(f"   Avg Decision Time: {perf.get('avg_decision_time_ms', 0):.0f}ms")
            
            # Show recent performance
            recent = stats.get('recent_performance', {})
            log.info(f"\n4. Recent Performance:")
            log.info(f"   Win Rate: {recent.get('win_rate', 0):.1%}")
            log.info(f"   Avg PnL: ${recent.get('avg_pnl', 0):.2f}")
            log.info(f"   Total Trades: {recent.get('total_trades', 0)}")
            log.info(f"   Wins: {recent.get('wins', 0)} | Losses: {recent.get('losses', 0)}")
            
            # Show adaptive thresholds
            thresholds = stats.get('adaptive_thresholds', {})
            log.info(f"\n5. Adaptive Thresholds:")
            log.info(f"   Min Score: {thresholds.get('min_score', 0):.1f}")
            log.info(f"   Min Confidence: {thresholds.get('min_confidence', 0):.0%}")
            log.info(f"   Min R:R: {thresholds.get('min_rr', 0):.1f}")
            
            # Determine if it's working
            total_decisions = perf.get('total_decisions', 0)
            fast_path_pct = perf.get('fast_path_percentage', 0)
            
            log.info("\n" + "=" * 60)
            log.info("VERDICT")
            log.info("=" * 60)
            
            if total_decisions == 0:
                log.warning("⏳ Autonomous system is enabled but hasn't made any decisions yet")
                log.info("   Wait for the next bot cycle (runs every 5 minutes)")
                log.info("   You should see [AUTONOMOUS] and [FAST_PATH] logs soon")
                return True
            
            elif fast_path_pct >= 80:
                log.info("✅ AUTONOMOUS SYSTEM IS WORKING PERFECTLY!")
                log.info(f"   {fast_path_pct:.1f}% of decisions using fast path")
                log.info(f"   Average decision time: {perf.get('avg_decision_time_ms', 0):.0f}ms")
                return True
            
            elif fast_path_pct >= 50:
                log.info("✅ Autonomous system is working")
                log.warning(f"   Fast path usage is {fast_path_pct:.1f}% (target: >85%)")
                log.info("   This may improve as the system learns")
                return True
            
            else:
                log.warning("⚠️  Autonomous system is enabled but fast path usage is low")
                log.info(f"   Fast path: {fast_path_pct:.1f}% (target: >85%)")
                log.info("   Most signals are edge cases requiring LLM review")
                return True
            
    except httpx.ConnectError:
        log.error("✗ Cannot connect to API server")
        log.info("   Make sure the bot is running: python main.py")
        return False
    except Exception as e:
        log.error(f"✗ Error checking status: {e}")
        import traceback
        traceback.print_exc()
        return False


async def check_logs_for_autonomous():
    """Check recent log file for autonomous system activity"""
    log.info("\n" + "=" * 60)
    log.info("CHECKING LOGS FOR AUTONOMOUS ACTIVITY")
    log.info("=" * 60)
    
    log_dir = Path(__file__).parent.parent / "logs"
    
    if not log_dir.exists():
        log.warning("✗ Log directory not found")
        return False
    
    log_files = list(log_dir.glob("apex_*.log"))
    if not log_files:
        log.warning("✗ No log files found")
        return False
    
    latest_log = max(log_files, key=lambda p: p.stat().st_mtime)
    
    try:
        with open(latest_log, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Look for autonomous system markers
        autonomous_markers = [
            "[AUTONOMOUS]",
            "[FAST_PATH]",
            "[LLM_BATCH]",
            "autonomous_orchestrator",
            "Fast path",
        ]
        
        matching_lines = []
        for line in lines[-200:]:  # Check last 200 lines
            if any(marker in line for marker in autonomous_markers):
                matching_lines.append(line.strip())
        
        if matching_lines:
            log.info(f"\n✓ Found {len(matching_lines)} autonomous system log entries")
            log.info("\nRecent autonomous activity:")
            for line in matching_lines[-10:]:  # Show last 10
                # Truncate long lines
                if len(line) > 120:
                    line = line[:120] + "..."
                log.info(f"   {line}")
            return True
        else:
            log.warning("✗ No autonomous system activity found in logs")
            log.info("   The bot may not have completed a cycle yet")
            log.info("   Wait a few minutes and check again")
            return False
            
    except Exception as e:
        log.error(f"✗ Error reading log file: {e}")
        return False


async def main():
    # Check API status
    api_ok = await check_autonomous_status()
    
    # Check logs
    logs_ok = await check_logs_for_autonomous()
    
    log.info("\n" + "=" * 60)
    log.info("SUMMARY")
    log.info("=" * 60)
    
    if api_ok and logs_ok:
        log.info("✅ Autonomous system is ACTIVE and WORKING")
        log.info("\nWhat to watch for:")
        log.info("  • [AUTONOMOUS] - Processing signals")
        log.info("  • [FAST_PATH] ✓ - Auto-approved signals")
        log.info("  • [FAST_PATH] ✗ - Auto-rejected signals")
        log.info("  • [LLM_BATCH] - Edge cases reviewed by LLM")
        log.info("  • Decision times < 1 second")
    elif api_ok:
        log.info("✅ Autonomous system is enabled")
        log.info("⏳ Waiting for first cycle to complete")
        log.info("\nCheck again in a few minutes")
    else:
        log.warning("⚠️  Autonomous system status unclear")
        log.info("\nTroubleshooting:")
        log.info("  1. Make sure bot is running: python main.py --autostart")
        log.info("  2. Wait for at least one bot cycle (5 minutes)")
        log.info("  3. Check dashboard at http://localhost:8000")


if __name__ == "__main__":
    asyncio.run(main())

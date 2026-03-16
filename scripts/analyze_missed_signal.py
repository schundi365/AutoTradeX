"""
Analyze why the bot missed a trading signal.
Checks recent decisions, market conditions, and rejection reasons.
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from loguru import logger as log


async def check_recent_decisions():
    """Check recent bot decisions for gold"""
    log.info("=" * 60)
    log.info("ANALYZING RECENT DECISIONS")
    log.info("=" * 60)
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8000/api/decisions?limit=50", timeout=10.0)
            
            if resp.status_code != 200:
                log.error("Failed to fetch decisions")
                return
            
            decisions = resp.json()
            
            # Filter for gold (XAUUSD)
            gold_decisions = [d for d in decisions if 'XAU' in d.get('symbol', '').upper()]
            
            if not gold_decisions:
                log.warning("⚠️  No recent decisions found for GOLD (XAUUSD)")
                log.info("   The bot may not have analyzed gold in recent cycles")
                return
            
            log.info(f"\nFound {len(gold_decisions)} recent gold decisions:\n")
            
            for i, decision in enumerate(gold_decisions[:10], 1):
                symbol = decision.get('symbol', 'N/A')
                dec = decision.get('decision', 'N/A')
                confidence = decision.get('confidence', 0)
                timestamp = decision.get('timestamp', 'N/A')
                context = decision.get('context', {})
                
                log.info(f"{i}. {symbol} - {dec} (confidence: {confidence:.0%})")
                log.info(f"   Time: {timestamp}")
                log.info(f"   Score: {context.get('score', 'N/A')}")
                log.info(f"   Direction: {context.get('direction', 'N/A')}")
                log.info(f"   ADX: {context.get('adx', 'N/A')}")
                log.info(f"   RSI: {context.get('rsi', 'N/A')}")
                log.info(f"   Reasoning: {context.get('reasoning', 'N/A')[:100]}...")
                log.info("")
                
    except Exception as e:
        log.error(f"Error checking decisions: {e}")


async def check_current_market_data():
    """Check current market data for gold"""
    log.info("=" * 60)
    log.info("CURRENT GOLD MARKET DATA")
    log.info("=" * 60)
    
    try:
        # Get current quote
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8000/api/ticker", timeout=10.0)
            
            if resp.status_code == 200:
                tickers = resp.json()
                gold_ticker = next((t for t in tickers if 'XAU' in t.get('symbol', '')), None)
                
                if gold_ticker:
                    log.info(f"\nCurrent Price: ${gold_ticker.get('price', 'N/A')}")
                    log.info(f"Change: {gold_ticker.get('change', 'N/A')}%")
                    log.info(f"Volume: {gold_ticker.get('volume', 'N/A')}")
                else:
                    log.warning("Gold ticker not found in current data")
                    
    except Exception as e:
        log.error(f"Error fetching market data: {e}")


async def analyze_logs_for_gold():
    """Analyze logs for gold signal analysis"""
    log.info("\n" + "=" * 60)
    log.info("ANALYZING LOGS FOR GOLD SIGNALS")
    log.info("=" * 60)
    
    log_dir = Path(__file__).parent.parent / "logs"
    
    if not log_dir.exists():
        log.warning("Log directory not found")
        return
    
    log_files = list(log_dir.glob("apex_*.log"))
    if not log_files:
        log.warning("No log files found")
        return
    
    latest_log = max(log_files, key=lambda p: p.stat().st_mtime)
    
    try:
        with open(latest_log, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Look for gold-related entries
        gold_lines = []
        for line in lines[-500:]:  # Check last 500 lines
            if 'XAU' in line.upper() or 'GOLD' in line.upper():
                gold_lines.append(line.strip())
        
        if not gold_lines:
            log.warning("⚠️  No gold-related log entries found in recent logs")
            log.info("   Possible reasons:")
            log.info("   1. Bot hasn't run a cycle recently")
            log.info("   2. Gold not in analyzed symbols list")
            log.info("   3. No signals generated for gold")
            return
        
        log.info(f"\nFound {len(gold_lines)} gold-related log entries")
        log.info("\nRecent gold activity:\n")
        
        # Show last 15 entries
        for line in gold_lines[-15:]:
            if len(line) > 150:
                line = line[:150] + "..."
            log.info(f"   {line}")
            
        # Look for rejection reasons
        rejection_lines = [l for l in gold_lines if 'REJECT' in l.upper() or 'NOGO' in l.upper() or 'FAILED' in l.upper()]
        
        if rejection_lines:
            log.info("\n" + "=" * 60)
            log.info("REJECTION REASONS")
            log.info("=" * 60)
            for line in rejection_lines[-5:]:
                if len(line) > 150:
                    line = line[:150] + "..."
                log.info(f"   {line}")
                
    except Exception as e:
        log.error(f"Error reading log file: {e}")


async def check_bot_cycle_timing():
    """Check when the bot last ran"""
    log.info("\n" + "=" * 60)
    log.info("BOT CYCLE TIMING")
    log.info("=" * 60)
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8000/api/status", timeout=5.0)
            
            if resp.status_code == 200:
                status = resp.json()
                bot_running = status.get('bot_running', False)
                
                log.info(f"\nBot Running: {bot_running}")
                
                if not bot_running:
                    log.warning("⚠️  Bot is NOT running!")
                    log.info("   Start the bot to catch future signals")
                else:
                    log.info("✓ Bot is running")
                    log.info("   Cycles run every 5 minutes")
                    log.info("   Next cycle will analyze current market conditions")
                    
    except Exception as e:
        log.error(f"Error checking bot status: {e}")


async def check_signal_filters():
    """Check current signal filter settings"""
    log.info("\n" + "=" * 60)
    log.info("SIGNAL FILTER SETTINGS")
    log.info("=" * 60)
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8000/api/config", timeout=5.0)
            
            if resp.status_code == 200:
                config = resp.json()
                risk = config.get('risk', {})
                strategy = config.get('strategy', {})
                
                log.info("\nRisk Filters:")
                log.info(f"   Min Signal Score: {risk.get('min_signal_score', 'N/A')}")
                log.info(f"   Min Confidence: {risk.get('min_confidence', 'N/A')}")
                log.info(f"   Min Risk/Reward: {risk.get('min_risk_reward', 'N/A')}")
                log.info(f"   Min ADX: {risk.get('min_adx', 'N/A')}")
                log.info(f"   Min ATR Ratio: {risk.get('min_atr_ratio', 'N/A')}")
                log.info(f"   Min Volume Ratio: {risk.get('min_volume_ratio', 'N/A')}")
                
                log.info("\nStrategy Settings:")
                log.info(f"   Enabled Strategies: {strategy.get('enabled_strategies', 'N/A')}")
                log.info(f"   Timeframes: {strategy.get('timeframes', 'N/A')}")
                
                # Check if filters are too strict
                min_score = risk.get('min_signal_score', 0)
                min_conf = risk.get('min_confidence', 0)
                min_rr = risk.get('min_risk_reward', 0)
                
                if min_score > 7.5:
                    log.warning(f"   ⚠️  Min score ({min_score}) is very high - may miss good signals")
                if min_conf > 0.75:
                    log.warning(f"   ⚠️  Min confidence ({min_conf}) is very high - may miss good signals")
                if min_rr > 2.5:
                    log.warning(f"   ⚠️  Min R:R ({min_rr}) is very high - may miss good signals")
                    
    except Exception as e:
        log.error(f"Error checking config: {e}")


async def check_autonomous_stats():
    """Check autonomous system stats"""
    log.info("\n" + "=" * 60)
    log.info("AUTONOMOUS SYSTEM STATS")
    log.info("=" * 60)
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8000/api/autonomous/stats", timeout=5.0)
            
            if resp.status_code == 200:
                stats = resp.json()
                
                if not stats.get('enabled', False):
                    log.info("Autonomous system not enabled")
                    return
                
                perf = stats.get('performance', {})
                thresholds = stats.get('adaptive_thresholds', {})
                
                log.info("\nCurrent Adaptive Thresholds:")
                log.info(f"   Min Score: {thresholds.get('min_score', 'N/A')}")
                log.info(f"   Min Confidence: {thresholds.get('min_confidence', 'N/A')}")
                log.info(f"   Min R:R: {thresholds.get('min_rr', 'N/A')}")
                
                log.info("\nRecent Performance:")
                log.info(f"   Total Decisions: {perf.get('total_decisions', 0)}")
                log.info(f"   Fast Path %: {perf.get('fast_path_percentage', 0):.1f}%")
                
                # Check if thresholds are too strict
                min_score = thresholds.get('min_score', 0)
                if min_score > 7.0:
                    log.warning(f"   ⚠️  Adaptive threshold for score ({min_score}) is high")
                    log.info("   System may have tightened due to recent losses")
                    
    except Exception as e:
        log.debug(f"Autonomous stats not available: {e}")


async def main():
    log.info("🔍 ANALYZING WHY BOT MISSED GOLD BREAKOUT SIGNAL\n")
    
    # Run all checks
    await check_bot_cycle_timing()
    await check_recent_decisions()
    await check_current_market_data()
    await check_signal_filters()
    await check_autonomous_stats()
    await analyze_logs_for_gold()
    
    # Summary
    log.info("\n" + "=" * 60)
    log.info("POSSIBLE REASONS FOR MISSED SIGNAL")
    log.info("=" * 60)
    
    log.info("\n1. TIMING ISSUES:")
    log.info("   • Bot runs every 5 minutes - may have missed the exact breakout moment")
    log.info("   • Breakout happened between cycles")
    log.info("   • Solution: Bot will catch it in next cycle if still valid")
    
    log.info("\n2. FILTER REJECTIONS:")
    log.info("   • Signal didn't meet minimum score/confidence/R:R thresholds")
    log.info("   • ADX too low (choppy market)")
    log.info("   • Volume too low")
    log.info("   • Solution: Check logs for specific rejection reason")
    
    log.info("\n3. RISK MANAGEMENT:")
    log.info("   • Max open trades reached")
    log.info("   • Daily drawdown limit hit")
    log.info("   • Correlation limit (too many correlated positions)")
    log.info("   • Solution: Close some positions or adjust limits")
    
    log.info("\n4. NEWS BLACKOUT:")
    log.info("   • High-impact news event within 30 minutes")
    log.info("   • Bot pauses trading during news")
    log.info("   • Solution: Wait for news event to pass")
    
    log.info("\n5. ADAPTIVE LEARNING:")
    log.info("   • System tightened thresholds due to recent losses")
    log.info("   • Being more selective to protect capital")
    log.info("   • Solution: Will loosen when performance improves")
    
    log.info("\n" + "=" * 60)
    log.info("RECOMMENDATIONS")
    log.info("=" * 60)
    
    log.info("\n• Check the logs above for specific rejection reasons")
    log.info("• Review recent decisions to see what filters failed")
    log.info("• Consider adjusting thresholds if too strict")
    log.info("• Wait for next bot cycle - it may catch the signal then")
    log.info("• Monitor autonomous stats for adaptive threshold changes")


if __name__ == "__main__":
    asyncio.run(main())

"""
Check if the bot is running and diagnose log streaming issues.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from loguru import logger as log


async def check_api_server():
    """Check if API server is running"""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8000/api/status", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                log.info("✓ API Server is running")
                log.info(f"  Bot running: {data.get('bot_running', False)}")
                log.info(f"  Open trades: {data.get('open_trades', 0)}")
                return True
            else:
                log.error(f"✗ API Server returned status {resp.status_code}")
                return False
    except Exception as e:
        log.error(f"✗ API Server is not running: {e}")
        log.info("\nTo start the server, run:")
        log.info("  python -m uvicorn api.server:app --reload --host 0.0.0.0 --port 8000")
        return False


async def check_bot_running():
    """Check if bot loop is running"""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8000/api/status", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                bot_running = data.get('bot_running', False)
                
                if bot_running:
                    log.info("✓ Bot loop is running")
                    return True
                else:
                    log.warning("✗ Bot loop is NOT running")
                    log.info("\nTo start the bot, either:")
                    log.info("  1. Click 'Start Bot' button in the dashboard")
                    log.info("  2. Run: curl -X POST http://localhost:8000/api/bot/start")
                    return False
    except Exception as e:
        log.error(f"Error checking bot status: {e}")
        return False


async def check_websocket():
    """Check if WebSocket endpoint is accessible"""
    try:
        import websockets
        
        async with websockets.connect("ws://localhost:8000/ws") as ws:
            log.info("✓ WebSocket connection successful")
            
            # Wait for a log message
            log.info("  Waiting for log messages (5 seconds)...")
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                log.info(f"  Received: {msg[:100]}...")
                return True
            except asyncio.TimeoutError:
                log.warning("  No log messages received in 5 seconds")
                log.info("  This is normal if the bot isn't actively processing")
                return True
                
    except ImportError:
        log.warning("✗ websockets library not installed")
        log.info("  Install with: pip install websockets")
        return False
    except Exception as e:
        log.error(f"✗ WebSocket connection failed: {e}")
        return False


async def test_log_generation():
    """Generate a test log to verify streaming"""
    try:
        from core.logger import get_agent_logger
        
        test_log = get_agent_logger("TEST")
        test_log.info("🧪 Test log message from diagnostic script")
        log.info("✓ Test log generated")
        
        return True
    except Exception as e:
        log.error(f"✗ Failed to generate test log: {e}")
        return False


async def check_log_files():
    """Check if log files are being written"""
    log_dir = Path(__file__).parent.parent / "logs"
    
    if not log_dir.exists():
        log.warning(f"✗ Log directory doesn't exist: {log_dir}")
        return False
    
    log_files = list(log_dir.glob("apex_*.log"))
    
    if not log_files:
        log.warning("✗ No log files found")
        return False
    
    latest_log = max(log_files, key=lambda p: p.stat().st_mtime)
    size = latest_log.stat().st_size
    
    log.info(f"✓ Log files found: {len(log_files)}")
    log.info(f"  Latest: {latest_log.name} ({size} bytes)")
    
    if size == 0:
        log.warning("  Warning: Latest log file is empty")
        return False
    
    # Show last few lines
    try:
        with open(latest_log, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if lines:
                log.info(f"  Last log entry: {lines[-1].strip()[:100]}...")
    except Exception as e:
        log.warning(f"  Could not read log file: {e}")
    
    return True


async def main():
    log.info("=" * 60)
    log.info("BOT STATUS & LOG DIAGNOSTIC")
    log.info("=" * 60)
    
    results = []
    
    # Check API server
    log.info("\n1. Checking API Server...")
    results.append(("API Server", await check_api_server()))
    
    if results[0][1]:  # If API server is running
        # Check bot loop
        log.info("\n2. Checking Bot Loop...")
        results.append(("Bot Loop", await check_bot_running()))
        
        # Check WebSocket
        log.info("\n3. Checking WebSocket Connection...")
        results.append(("WebSocket", await check_websocket()))
    
    # Check log files
    log.info("\n4. Checking Log Files...")
    results.append(("Log Files", await check_log_files()))
    
    # Test log generation
    log.info("\n5. Testing Log Generation...")
    results.append(("Log Generation", await test_log_generation()))
    
    # Summary
    log.info("\n" + "=" * 60)
    log.info("DIAGNOSTIC SUMMARY")
    log.info("=" * 60)
    
    for name, status in results:
        status_str = "✓ PASS" if status else "✗ FAIL"
        log.info(f"{status_str} - {name}")
    
    passed = sum(1 for _, status in results if status)
    total = len(results)
    
    log.info("=" * 60)
    log.info(f"TOTAL: {passed}/{total} checks passed")
    log.info("=" * 60)
    
    if passed < total:
        log.info("\nTROUBLESHOOTING:")
        
        if not results[0][1]:  # API server not running
            log.info("• Start the API server first:")
            log.info("  python -m uvicorn api.server:app --reload --host 0.0.0.0 --port 8000")
        
        elif results[0][1] and not results[1][1]:  # Bot not running
            log.info("• Start the bot from the dashboard or via API:")
            log.info("  curl -X POST http://localhost:8000/api/bot/start")
        
        log.info("\n• If logs still don't appear in dashboard:")
        log.info("  1. Check browser console for WebSocket errors")
        log.info("  2. Refresh the dashboard page")
        log.info("  3. Check that port 8000 is not blocked by firewall")


if __name__ == "__main__":
    asyncio.run(main())

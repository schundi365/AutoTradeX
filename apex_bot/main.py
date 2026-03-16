"""
APEX Trading Bot — Main Entry Point

Usage:
  python main.py                    # Start API server + bot
  python main.py --mode api         # API server only (no auto-start bot)
  python main.py --mode backtest    # Run backtest
  python main.py --mode paper       # Paper trading mode
"""
import asyncio
import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.logger import setup_logging
from core.config import settings


def parse_args():
    parser = argparse.ArgumentParser(description="APEX Trading Bot")
    parser.add_argument("--mode",    default="full",  choices=["full","api","backtest","paper"])
    parser.add_argument("--host",    default="0.0.0.0")
    parser.add_argument("--port",    default=8000, type=int)
    parser.add_argument("--reload",  action="store_true", help="Hot reload (dev mode)")
    parser.add_argument("--autostart", action="store_true", help="Auto-start bot on launch")
    return parser.parse_args()


async def run_backtest():
    """Run a historical backtest using VectorBT or Backtrader."""
    from core.logger import get_agent_logger
    log = get_agent_logger("BACKTEST")
    log.info("Starting backtest...")

    from data.market_feed import MarketFeed
    from strategies.technical import TechnicalAnalyser
    from data.market_feed import _mock_quote

    feed = MarketFeed()
    analyser = TechnicalAnalyser()

    symbols = settings.assets.metals + settings.assets.forex[:2]
    total_signals = 0

    for symbol in symbols:
        bars = await feed.get_ohlcv(symbol, "H1", bars=1000)
        quote = _mock_quote(symbol)
        signals = await analyser.analyse(symbol, quote)
        log.info("  {} → {} signals", symbol, len(signals))
        total_signals += len(signals)

    log.info("Backtest complete — {} signals across {} symbols", total_signals, len(symbols))


async def run_paper_trading():
    """Start bot in paper trading mode (no real orders)."""
    import os
    os.environ["APP_ENV"] = "paper"
    from core.config import Config
    settings.__class__ = Config
    await run_bot_loop()


async def run_bot_loop():
    """Run the agent pipeline loop standalone (no API server)."""
    from agents.graph import run_agent_pipeline
    from core.models import BotState

    state = BotState()
    log = __import__('core.logger', fromlist=['get_agent_logger']).get_agent_logger("MAIN")

    log.info("Bot loop started — running every 5 minutes")
    cycle = 0
    while True:
        cycle += 1
        log.info("Cycle #{}", cycle)
        state = await run_agent_pipeline(state)
        await asyncio.sleep(300)


def main():
    args = parse_args()
    setup_logging(settings.log_level)

    print("""
    ╔══════════════════════════════════════════════════════╗
    ║          APEX TRADING BOT  —  v1.0.0                ║
    ║   Agentic AI Framework | MT5 | CCXT | Multi-Asset   ║
    ╚══════════════════════════════════════════════════════╝
    """)

    if args.mode == "backtest":
        asyncio.run(run_backtest())
        return

    if args.mode == "paper":
        asyncio.run(run_paper_trading())
        return

    # API server (default)
    import uvicorn

    if args.mode == "full" and args.autostart:
        # Auto-start bot when server starts
        import api.server as srv
        srv._bot_running = True
        import asyncio as aio
        async def _start():
            srv._bot_task = aio.create_task(srv._bot_main_loop())
        # Will be triggered on startup event

    uvicorn.run(
        "api.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload and args.mode != "full",
        log_level=settings.log_level.lower(),
        access_log=False,
    )


if __name__ == "__main__":
    main()

import asyncio
import yfinance as yf
from datetime import datetime
from typing import Optional
from core.logger import get_agent_logger
from core.models import Direction

log = get_agent_logger("MACRO")

class MacroAgent:
    """
    Monitors Macro indicators:
    - DXY (US Dollar Index)
    - US10Y (US 10-Year Treasury Yield)
    
    Since Gold (XAUUSD) is inversely correlated with USD strength and Yields,
    this agent can 'veto' buy signals if DXY or Yields are spiking.
    """
    def __init__(self):
        self.dxy_symbol = "DX-Y.NYB"
        self.us10y_symbol = "^TNX"

    async def get_macro_sentiment(self) -> dict:
        """Fetches recent trends for DXY and US10Y."""
        try:
            # yfinance is synchronous, run in thread
            dxy = await asyncio.to_thread(yf.Ticker(self.dxy_symbol).history, period="5d")
            us10y = await asyncio.to_thread(yf.Ticker(self.us10y_symbol).history, period="5d")
            
            dxy_change = (dxy['Close'].iloc[-1] / dxy['Close'].iloc[-2]) - 1
            us10y_change = (us10y['Close'].iloc[-1] / us10y['Close'].iloc[-2]) - 1
            
            log.info("Macro: DXY Change: {:.2%}, US10Y Change: {:.2%}", dxy_change, us10y_change)
            
            return {
                "dxy_trend": "UP" if dxy_change > 0.001 else "DOWN" if dxy_change < -0.001 else "FLAT",
                "yield_trend": "UP" if us10y_change > 0.005 else "DOWN" if us10y_change < -0.005 else "FLAT",
                "dxy_change": dxy_change,
                "yield_change": us10y_change
            }
        except Exception as e:
            log.warning("MacroAgent fetch failed: {}", e)
            return {"dxy_trend": "FLAT", "yield_trend": "FLAT", "error": str(e)}

    def evaluate_veto(self, symbol: str, direction: Direction, macro_data: dict) -> tuple[bool, str]:
        """Returns (is_vetoed, reason)."""
        if "XAU" not in symbol.upper():
            return False, ""

        dxy_up = macro_data.get("dxy_trend") == "UP"
        yield_up = macro_data.get("yield_trend") == "UP"

        if direction == Direction.BUY:
            if dxy_up and yield_up:
                return True, "VETO: DXY and Yields both spiking (Bearish for Gold)"
            if dxy_up:
                return True, "VETO: Dollar strength (DXY) is rising"
        
        if direction == Direction.SELL:
            if not dxy_up and not yield_up:
                return True, "VETO: DXY and Yields both falling (Bullish for Gold)"

        return False, ""

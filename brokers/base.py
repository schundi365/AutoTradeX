"""
APEX Bot — Broker Abstraction Layer
All brokers implement the same BaseBroker interface.
Swap brokers with zero strategy code changes.
"""
from __future__ import annotations
import asyncio
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional

from core.models import (
    Trade, TradeStatus, Direction, OrderType,
    AccountInfo, Quote, BrokerName, AssetClass
)
from core.logger import get_agent_logger

log = get_agent_logger("BROKER")


# ═══════════════════════════════════════════════════════
#  BASE INTERFACE — every broker must implement these
# ═══════════════════════════════════════════════════════

class BaseBroker(ABC):
    name: BrokerName
    connected: bool = False

    @abstractmethod
    async def connect(self) -> bool:
        """Establish broker connection."""

    @abstractmethod
    async def disconnect(self):
        """Close broker connection."""

    @abstractmethod
    async def get_account(self) -> AccountInfo:
        """Return current account balance/equity/margin."""

    @abstractmethod
    async def get_quote(self, symbol: str) -> Quote:
        """Return live bid/ask for a symbol."""

    @abstractmethod
    async def place_order(self, trade: Trade) -> Trade:
        """Submit an order; returns updated Trade with broker_order_id."""

    @abstractmethod
    async def close_trade(self, trade: Trade) -> Trade:
        """Close an open position at market."""

    @abstractmethod
    async def modify_trade(self, trade: Trade, sl: float, tp: float) -> Trade:
        """Modify SL/TP of an open trade."""

    @abstractmethod
    async def get_open_trades(self) -> list[Trade]:
        """Return all currently open positions."""

    @abstractmethod
    async def get_historical_data(
        self, symbol: str, timeframe: str, bars: int = 500
    ) -> list[dict]:
        """Return OHLCV bars as list of dicts."""

    @abstractmethod
    async def get_calendar_events(self, hours_ahead: int = 48) -> list[CalendarEvent]:
        """Return upcoming economic calendar events."""

    async def health_check(self) -> bool:
        """Ping broker. Returns True if healthy."""
        try:
            await self.get_account()
            return True
        except Exception as e:
            log.warning("Broker {} health check failed: {}", self.name, e)
            return False


# ═══════════════════════════════════════════════════════
#  MT5 BROKER
# ═══════════════════════════════════════════════════════

class MT5Broker(BaseBroker):
    name = BrokerName.MT5

    def __init__(self, login: int, password: str, server: str, path: str = ""):
        self.login    = login
        self.password = password
        self.server   = server
        self.path     = path
        self._mt5     = None  # lazy import (Windows only)

    async def connect(self) -> bool:
        try:
            import MetaTrader5 as mt5
            self._mt5 = mt5
            kwargs = dict(login=self.login, password=self.password, server=self.server)
            if self.path:
                kwargs["path"] = self.path
            if not await asyncio.to_thread(mt5.initialize, **kwargs):
                raise ConnectionError(mt5.last_error())
            info = await asyncio.to_thread(mt5.account_info)
            self.connected = True
            log.info("MT5 connected — Account: {} | Balance: ${:.2f}", info.login, info.balance)
            return True
        except ImportError:
            log.warning("MetaTrader5 package not available (non-Windows). Using mock.")
            self.connected = True   # dev mode
            return True
        except Exception as e:
            log.error("MT5 connection failed: {}", e)
            return False

    async def disconnect(self):
        if self._mt5:
            await asyncio.to_thread(self._mt5.shutdown)
        self.connected = False
        log.info("MT5 disconnected")

    async def get_account(self) -> AccountInfo:
        if not self._mt5:
            return _mock_account(BrokerName.MT5)
        info = await asyncio.to_thread(self._mt5.account_info)
        if not info:
            log.error("MT5 account_info() returned None - connection may be lost")
            # Try to reconnect
            if await self.connect():
                info = await asyncio.to_thread(self._mt5.account_info)
            if not info:
                log.error("MT5 reconnection failed - using mock account")
                return _mock_account(BrokerName.MT5)
        return AccountInfo(
            broker=BrokerName.MT5,
            balance=info.balance,
            equity=info.equity,
            margin=info.margin,
            free_margin=info.margin_free,
            margin_pct=info.margin_level,
            currency=info.currency,
        )

    async def get_quote(self, symbol: str) -> Quote:
        if not self._mt5:
            return _mock_quote(symbol)
        tick = await asyncio.to_thread(self._mt5.symbol_info_tick, symbol)
        if not tick:
            raise ValueError(f"MT5: no tick for {symbol}")
        return Quote(
            symbol=symbol,
            bid=tick.bid,
            ask=tick.ask,
            spread=round(tick.ask - tick.bid, 5),
        )

    def _normalize_volume(self, symbol: str, volume: float) -> float:
        """Round lot size to nearest valid step for the symbol (MT5 requirements)."""
        if not self._mt5:
            return volume
        info = self._mt5.symbol_info(symbol)
        if not info:
            return volume
            
        step = info.volume_step
        min_v = info.volume_min
        max_v = info.volume_max
        
        # Round to step
        norm = round(round(volume / step) * step, 2)
        # Clamp
        norm = max(min_v, min(norm, max_v))
        
        if norm != volume:
            log.debug("MT5: Normalized volume for {} from {} to {}", symbol, volume, norm)
        return norm

    def _normalize_price(self, symbol: str, price: float) -> float:
        """Round price to the correct number of digits for the symbol (MT5 requirements)."""
        if not self._mt5:
            return price
        info = self._mt5.symbol_info(symbol)
        if not info:
            return price
        
        digits = info.digits
        norm = round(price, digits)
        
        if norm != price:
            log.debug("MT5: Normalized price for {} from {} to {} (digits={})", symbol, price, norm, digits)
        return norm

    async def place_order(self, trade: Trade) -> Trade:
        if not self._mt5:
            return _mock_place(trade)
        mt5 = self._mt5
        action = mt5.TRADE_ACTION_DEAL
        order_type = mt5.ORDER_TYPE_BUY if trade.direction == Direction.BUY else mt5.ORDER_TYPE_SELL

        # Try multiple filling modes (MT5 brokers are picky about this)
        filling_modes = [
            mt5.ORDER_FILLING_IOC,
            mt5.ORDER_FILLING_FOK,
            mt5.ORDER_FILLING_RETURN
        ]
        
        # Ensure latest price is used
        quote = await self.get_quote(trade.symbol)
        price = quote.ask if trade.direction == Direction.BUY else quote.bid
        
        last_error = ""
        for mode in filling_modes:
            request = {
                "action":    action,
                "symbol":    trade.symbol,
                "volume":    self._normalize_volume(trade.symbol, trade.lot_size),
                "type":      order_type,
                "price":     self._normalize_price(trade.symbol, price),
                "sl":        self._normalize_price(trade.symbol, trade.stop_loss),
                "tp":        self._normalize_price(trade.symbol, trade.take_profit),
                "deviation": 20,
                "magic":     888888,
                "comment":   f"APEX:{trade.strategy}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mode,
            }
            
            result = await asyncio.to_thread(mt5.order_send, request)
            
            if result is None:
                last_error = "mt5.order_send returned None"
                continue
                
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                trade.broker_order_id = str(result.order)
                trade.status = TradeStatus.OPEN
                trade.open_time = datetime.utcnow()
                log.success("TRADE OPENED: {} {} {} @ {} (mode={})", 
                            trade.direction, trade.lot_size, trade.symbol, trade.entry_price, mode)
                return trade
            
            # If error is specifically about filling mode, try next one
            # 10030 = TRADE_RETCODE_INVALID_FILL
            if result.retcode == 10030:
                log.warning("MT5: Filling mode {} not supported for {}, trying next...", mode, trade.symbol)
                last_error = f"retcode={result.retcode} | {result.comment}"
                continue
            else:
                # Other error (balance, price, etc.) - fail fast
                raise RuntimeError(f"MT5 order failed: retcode={result.retcode} | {result.comment}")

        raise RuntimeError(f"MT5 order failed after trying all filling modes: {last_error}")

    async def close_trade(self, trade: Trade) -> Trade:
        if not self._mt5:
            trade.status = TradeStatus.CLOSED
            trade.close_time = datetime.utcnow()
            return trade
        # Reverse direction to close
        mt5 = self._mt5
        close_type = mt5.ORDER_TYPE_SELL if trade.direction == Direction.BUY else mt5.ORDER_TYPE_BUY
        quote = await self.get_quote(trade.symbol)
        price = quote.bid if trade.direction == Direction.BUY else quote.ask

        request = {
            "action":   mt5.TRADE_ACTION_DEAL,
            "symbol":   trade.symbol,
            "volume":   self._normalize_volume(trade.symbol, trade.lot_size),
            "type":     close_type,
            "position": int(trade.broker_order_id),
            "price":    self._normalize_price(trade.symbol, price),
            "deviation": 20,
            "magic":    888888,
            "comment":  "APEX:CLOSE",
        }
        result = await asyncio.to_thread(mt5.order_send, request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            trade.status = TradeStatus.CLOSED
            trade.close_price = price
            trade.close_time = datetime.utcnow()
        return trade

    async def modify_trade(self, trade: Trade, sl: float, tp: float) -> Trade:
        trade.stop_loss = sl
        trade.take_profit = tp
        if not self._mt5 or not trade.broker_order_id:
            return trade
        mt5 = self._mt5
        try:
            ticket = int(trade.broker_order_id)
        except (TypeError, ValueError):
            log.warning("[MT5] modify_trade: invalid broker_order_id '{}' for {}", trade.broker_order_id, trade.symbol)
            return trade
            
        # Normalize prices for MT5 (crucial for stocks like AAPL)
        norm_sl = self._normalize_price(trade.symbol, sl)
        norm_tp = self._normalize_price(trade.symbol, tp)
            
        request = {
            "action":   mt5.TRADE_ACTION_SLTP,
            "symbol":   trade.symbol,
            "sl":       norm_sl,
            "tp":       norm_tp,
            "position": ticket,
        }
        result = await asyncio.to_thread(mt5.order_send, request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            retcode = result.retcode if result else "None"
            comment = result.comment if result else "No comment"
            log.warning("[MT5] modify_trade SL/TP failed for {} ticket={}: retcode={} ({})", 
                        trade.symbol, ticket, retcode, comment)
        return trade

    @staticmethod
    def _symbol_asset_class(symbol: str) -> AssetClass:
        s = symbol.upper()
        if any(k in s for k in ("XAU", "XAG", "XPT", "GOLD", "SILVER")):
            return AssetClass.METAL
        if any(k in s for k in ("BTC", "ETH", "SOL", "BNB", "XRP", "LTC", "ADA", "DOT", "AVAX")):
            return AssetClass.CRYPTO
        if any(k in s for k in ("US30", "SPX", "NAS", "GER40", "UK100", "JPN225", "DAX", "E30", "E50")):
            return AssetClass.INDEX
        if any(k in s for k in ("AAPL", "NVDA", "MSFT", "TSLA", "AMZN", "GOOGL", "META")):
            return AssetClass.STOCK
        return AssetClass.FOREX

    async def get_open_trades(self) -> list[Trade]:
        if not self._mt5:
            return []
        positions = await asyncio.to_thread(self._mt5.positions_get)
        trades = []
        for p in (positions or []):
            trades.append(Trade(
                id=str(p.ticket),
                broker=BrokerName.MT5,
                symbol=p.symbol,
                asset_class=self._symbol_asset_class(p.symbol),
                direction=Direction.BUY if p.type == 0 else Direction.SELL,
                lot_size=p.volume,
                entry_price=p.price_open,
                current_price=p.price_current,
                stop_loss=p.sl,
                take_profit=p.tp,
                status=TradeStatus.OPEN,
                open_time=datetime.fromtimestamp(p.time),
                pnl=p.profit,
                broker_order_id=str(p.ticket),
            ))
        return trades

    async def get_deal_history(self, days: int = 90) -> list[dict]:
        """Return closed trades from MT5 deal history as plain dicts (last N days).
        Only OUT deals (entry=1) are included — these carry the realized P&L.
        """
        if not self._mt5:
            return []
        mt5 = self._mt5
        from_date = datetime.utcnow() - timedelta(days=days)
        to_date = datetime.utcnow()
        deals = await asyncio.to_thread(mt5.history_deals_get, from_date, to_date)
        if not deals:
            return []
        result = []
        for d in deals:
            # entry 1 = DEAL_ENTRY_OUT (position close) — carries the realized P&L
            if getattr(d, "entry", -1) != 1:
                continue
            if getattr(d, "profit", 0.0) == 0.0 and getattr(d, "volume", 0.0) == 0.0:
                continue
            symbol = getattr(d, "symbol", "") or ""
            result.append({
                "id":          str(getattr(d, "ticket", "")),
                "symbol":      symbol,
                "direction":   "BUY" if getattr(d, "type", 1) == 1 else "SELL",
                "entry_price": float(getattr(d, "price", 0.0)),
                "close_price": float(getattr(d, "price", 0.0)),
                "lot_size":    float(getattr(d, "volume", 0.0)),
                "pnl":         float(getattr(d, "profit", 0.0)),
                "strategy":    "mt5",
                "status":      "CLOSED",
                "open_time":   datetime.fromtimestamp(getattr(d, "time", 0)).isoformat(),
                "close_time":  datetime.fromtimestamp(getattr(d, "time", 0)).isoformat(),
                "asset_class": self._symbol_asset_class(symbol).value,
            })
        return result

    async def get_historical_data(self, symbol: str, timeframe: str, bars: int = 500) -> list[dict]:
        if not self._mt5:
            return _mock_ohlcv(bars)
        mt5 = self._mt5
        TF_MAP = {"M1":mt5.TIMEFRAME_M1,"M5":mt5.TIMEFRAME_M5,"M15":mt5.TIMEFRAME_M15,
                  "M30":mt5.TIMEFRAME_M30,"H1":mt5.TIMEFRAME_H1,"H4":mt5.TIMEFRAME_H4,
                  "D1":mt5.TIMEFRAME_D1}
        tf = TF_MAP.get(timeframe, mt5.TIMEFRAME_H1)
        rates = await asyncio.to_thread(mt5.copy_rates_from_pos, symbol, tf, 0, bars)
        return [{"time":r[0],"open":r[1],"high":r[2],"low":r[3],"close":r[4],"volume":r[5]} for r in rates]

    async def get_calendar_events(self, hours_ahead: int = 48) -> list[CalendarEvent]:
        from core.models import CalendarEvent, NewsImpact
        if not self._mt5 or not hasattr(self._mt5, "calendar_value_get"):
            log.warning("MT5: calendar_value_get not available in this library version. Returning empty.")
            return []
        
        mt5 = self._mt5
        dt_from = datetime.utcnow()
        dt_to = dt_from + timedelta(hours=hours_ahead)
        
        try:
            # MT5 calendar is powerful but complex; we fetch 'values' for the period
            values = await asyncio.to_thread(mt5.calendar_value_get, dt_from, dt_to)
            if values is None:
                return []
                
            events = []
            # MT5 calendar_value_get returns events with IDs. 
            # We need to map importance: 0=None, 1=Low, 2=Moderate, 3=High
            IMPACT_MAP = {
                mt5.CALENDAR_IMPORTANCE_HIGH: NewsImpact.HIGH,
                mt5.CALENDAR_IMPORTANCE_MODERATE: NewsImpact.MEDIUM,
                mt5.CALENDAR_IMPORTANCE_LOW: NewsImpact.LOW,
                mt5.CALENDAR_IMPORTANCE_NONE: NewsImpact.LOW
            }
            
            for v in values:
                impact = IMPACT_MAP.get(v.importance, NewsImpact.LOW)
                events.append(CalendarEvent(
                    id=str(v.id),
                    title=v.event_name,
                    currency=v.currency,
                    impact=impact,
                    scheduled=datetime.fromtimestamp(v.time),
                    previous=str(v.prev_value) if v.prev_value else None,
                    forecast=str(v.forecast_value) if v.forecast_value else None,
                ))
            return events
        except Exception as e:
            log.error("MT5 calendar fetch failed: {}", e)
            return []


# ═══════════════════════════════════════════════════════
#  CCXT BROKER (Crypto)
# ═══════════════════════════════════════════════════════

class CCXTBroker(BaseBroker):
    name = BrokerName.CCXT

    def __init__(self, exchange_id: str, api_key: str, secret: str, sandbox: bool = True):
        self.exchange_id = exchange_id
        self.api_key     = api_key
        self.secret      = secret
        self.sandbox     = sandbox
        self._exchange   = None

    async def connect(self) -> bool:
        try:
            import ccxt.async_support as ccxt
            exchange_class = getattr(ccxt, self.exchange_id)
            self._exchange = exchange_class({
                "apiKey": self.api_key,
                "secret": self.secret,
                "enableRateLimit": True,
                "options": {"defaultType": "future"},
            })
            if self.sandbox:
                self._exchange.set_sandbox_mode(True)
            await self._exchange.load_markets()
            self.connected = True
            log.info("CCXT {} connected — {} markets loaded", self.exchange_id, len(self._exchange.markets))
            return True
        except Exception as e:
            log.error("CCXT connection failed: {}", e)
            return False

    async def disconnect(self):
        if self._exchange:
            await self._exchange.close()
        self.connected = False

    async def get_account(self) -> AccountInfo:
        if not self._exchange:
            return _mock_account(BrokerName.CCXT)
        balance = await self._exchange.fetch_balance()
        usdt = balance.get("USDT", {})
        total = usdt.get("total", 0.0)
        free  = usdt.get("free", 0.0)
        return AccountInfo(
            broker=BrokerName.CCXT,
            balance=total,
            equity=total,
            margin=total - free,
            free_margin=free,
            margin_pct=0.0,
            currency="USDT",
        )

    async def get_quote(self, symbol: str) -> Quote:
        if not self._exchange:
            return _mock_quote(symbol)
        ticker = await self._exchange.fetch_ticker(symbol)
        return Quote(
            symbol=symbol,
            bid=ticker["bid"] or ticker["last"],
            ask=ticker["ask"] or ticker["last"],
            spread=0.0,
        )

    async def place_order(self, trade: Trade) -> Trade:
        if not self._exchange:
            return _mock_place(trade)
        side = "buy" if trade.direction == Direction.BUY else "sell"
        order = await self._exchange.create_order(
            symbol=trade.symbol,
            type="market",
            side=side,
            amount=trade.lot_size,
            params={"stopLoss": {"triggerPrice": trade.stop_loss},
                    "takeProfit": {"triggerPrice": trade.take_profit}},
        )
        trade.broker_order_id = order["id"]
        trade.status = TradeStatus.OPEN
        trade.open_time = datetime.utcnow()
        log.success("TRADE OPENED (CCXT): {} {} {} @ ~{}", side.upper(), trade.lot_size, trade.symbol, trade.entry_price)
        return trade

    async def close_trade(self, trade: Trade) -> Trade:
        if not self._exchange:
            trade.status = TradeStatus.CLOSED
            return trade
        side = "sell" if trade.direction == Direction.BUY else "buy"
        await self._exchange.create_order(trade.symbol, "market", side, trade.lot_size,
                                          params={"reduceOnly": True})
        trade.status = TradeStatus.CLOSED
        trade.close_time = datetime.utcnow()
        return trade

    async def modify_trade(self, trade: Trade, sl: float, tp: float) -> Trade:
        trade.stop_loss = sl
        trade.take_profit = tp
        return trade  # Modify via separate SL/TP orders on most exchanges

    async def get_open_trades(self) -> list[Trade]:
        if not self._exchange:
            return []
        positions = await self._exchange.fetch_positions()
        trades = []
        for p in positions:
            if p.get("contracts", 0) > 0:
                trades.append(Trade(
                    id=str(p.get("id", uuid.uuid4())),
                    broker=BrokerName.CCXT,
                    symbol=p["symbol"],
                    asset_class=AssetClass.CRYPTO,
                    direction=Direction.BUY if p["side"] == "long" else Direction.SELL,
                    lot_size=p["contracts"],
                    entry_price=p["entryPrice"] or 0,
                    current_price=p["markPrice"],
                    stop_loss=0.0,
                    take_profit=0.0,
                    status=TradeStatus.OPEN,
                    pnl=p.get("unrealizedPnl", 0),
                ))
        return trades

    async def get_historical_data(self, symbol: str, timeframe: str, bars: int = 500) -> list[dict]:
        if not self._exchange:
            return _mock_ohlcv(bars)
        TF_MAP = {"M1":"1m","M5":"5m","M15":"15m","H1":"1h","H4":"4h","D1":"1d"}
        tf = TF_MAP.get(timeframe, "1h")
        ohlcv = await self._exchange.fetch_ohlcv(symbol, tf, limit=bars)
        return [{"time":c[0]//1000,"open":c[1],"high":c[2],"low":c[3],"close":c[4],"volume":c[5]} for c in ohlcv]

    async def get_calendar_events(self, hours_ahead: int = 48) -> list[CalendarEvent]:
        return [] # CCXT doesn't usually provide economic calendars


# ═══════════════════════════════════════════════════════
#  PAPER BROKER (no-cost simulation)
# ═══════════════════════════════════════════════════════

class PaperBroker(BaseBroker):
    """In-memory paper trading broker for testing."""
    name = BrokerName.PAPER

    def __init__(self, starting_balance: float = 10_000.0):
        self._balance = starting_balance
        self._trades:  list[Trade] = []

    async def connect(self) -> bool:
        self.connected = True
        log.info("Paper broker connected — Starting balance: ${:.2f}", self._balance)
        return True

    async def disconnect(self):
        self.connected = False

    async def get_account(self) -> AccountInfo:
        return _mock_account(BrokerName.PAPER, self._balance)

    async def get_quote(self, symbol: str) -> Quote:
        return _mock_quote(symbol)

    async def place_order(self, trade: Trade) -> Trade:
        trade.broker_order_id = str(uuid.uuid4())[:8]
        trade.status = TradeStatus.OPEN
        trade.open_time = datetime.utcnow()
        self._trades.append(trade)
        log.success("TRADE PAPER: {} {} {} @ {}", trade.direction, trade.lot_size, trade.symbol, trade.entry_price)
        return trade

    async def close_trade(self, trade: Trade) -> Trade:
        quote = await self.get_quote(trade.symbol)
        trade.close_price = quote.mid
        trade.close_time = datetime.utcnow()
        trade.status = TradeStatus.CLOSED
        return trade

    async def modify_trade(self, trade: Trade, sl: float, tp: float) -> Trade:
        trade.stop_loss = sl
        trade.take_profit = tp
        return trade

    async def get_open_trades(self) -> list[Trade]:
        return [t for t in self._trades if t.status == TradeStatus.OPEN]

    async def get_historical_data(self, symbol: str, timeframe: str, bars: int = 500) -> list[dict]:
        return _mock_ohlcv(bars)

    async def get_calendar_events(self, hours_ahead: int = 48) -> list[CalendarEvent]:
        # Return mock calendar in paper mode
        from data.market_feed import _mock_calendar
        return _mock_calendar()


# ═══════════════════════════════════════════════════════
#  BROKER FACTORY
# ═══════════════════════════════════════════════════════

class BrokerFactory:
    """
    Create and manage multiple broker instances.
    Usage:
        factory = BrokerFactory(settings)
        mt5  = factory.get("MT5")
        ccxt = factory.get("CCXT")
    """
    def __init__(self, settings):
        self._cfg = settings
        self._brokers: dict[str, BaseBroker] = {}

    def get(self, name: BrokerName | str) -> BaseBroker:
        name = BrokerName(name)
        if name not in self._brokers:
            self._brokers[name] = self._build(name)
        return self._brokers[name]

    def _build(self, name: BrokerName) -> BaseBroker:
        cfg = self._cfg
        if cfg.is_paper:
            return PaperBroker()
        if name == BrokerName.MT5:
            return MT5Broker(cfg.mt5_login, cfg.mt5_password, cfg.mt5_server, cfg.mt5_path)
        if name == BrokerName.CCXT:
            return CCXTBroker(cfg.exchange_id, cfg.exchange_api_key, cfg.exchange_secret, cfg.exchange_sandbox)
        raise ValueError(f"Unknown broker: {name}")

    async def connect_all(self):
        for b in self._brokers.values():
            await b.connect()

    async def disconnect_all(self):
        for b in self._brokers.values():
            await b.disconnect()


# ═══════════════════════════════════════════════════════
#  MOCK HELPERS (used when broker not available / dev)
# ═══════════════════════════════════════════════════════

import random

def _mock_account(broker: BrokerName, balance: float = 50_000.0) -> AccountInfo:
    return AccountInfo(broker=broker, balance=balance, equity=balance*1.04,
                       margin=balance*0.04, free_margin=balance*0.96, margin_pct=4.0)

def _mock_quote(symbol: str) -> Quote:
    prices = {"XAUUSD":2318.4,"BTCUSD":68200,"EURUSD":1.0842,"USOIL":78.92,"NVDA":890.2}
    p = prices.get(symbol, 100.0) * (1 + random.uniform(-0.0002, 0.0002))
    return Quote(symbol=symbol, bid=round(p,5), ask=round(p*1.0001,5), spread=round(p*0.0001,5))

def _mock_place(trade: Trade) -> Trade:
    trade.broker_order_id = str(uuid.uuid4())[:8]
    trade.status = TradeStatus.OPEN
    trade.open_time = datetime.utcnow()
    return trade

def _mock_ohlcv(bars: int) -> list[dict]:
    import time, math
    now = int(time.time())
    data, price = [], 2000.0
    for i in range(bars):
        price += random.uniform(-5, 5)
        o = price
        h = price + random.uniform(0, 10)
        l = price - random.uniform(0, 10)
        c = random.uniform(l, h)
        data.append({"time": now - (bars-i)*3600, "open":o,"high":h,"low":l,"close":c,"volume":random.uniform(100,10000)})
    return data

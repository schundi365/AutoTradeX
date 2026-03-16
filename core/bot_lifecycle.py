"""
APEX Bot — Bot Lifecycle Manager
Manages bot state (running/stopped/paused) and provides control interface.
"""
from __future__ import annotations
import time
from datetime import datetime
from enum import Enum
from dataclasses import dataclass
from typing import Optional
from core.logger import get_agent_logger

log = get_agent_logger("BOT_LIFECYCLE")


class BotState(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


@dataclass
class BotStatus:
    state: BotState
    start_time: Optional[datetime] = None
    stop_time: Optional[datetime] = None
    pause_time: Optional[datetime] = None
    error_message: Optional[str] = None
    active_positions: int = 0
    pending_orders: int = 0
    
    @property
    def uptime_seconds(self) -> int:
        if self.state == BotState.RUNNING and self.start_time:
            return int((datetime.utcnow() - self.start_time).total_seconds())
        return 0
    
    def to_dict(self) -> dict:
        return {
            "status": self.state.value,
            "uptime_seconds": self.uptime_seconds,
            "last_started": self.start_time.isoformat() if self.start_time else None,
            "last_stopped": self.stop_time.isoformat() if self.stop_time else None,
            "active_positions": self.active_positions,
            "pending_orders": self.pending_orders,
            "error_message": self.error_message
        }


class BotLifecycleManager:
    """
    Singleton manager for bot lifecycle control.
    Tracks bot state and provides start/stop/pause controls.
    """
    _instance: Optional[BotLifecycleManager] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.status = BotStatus(state=BotState.STOPPED)
        self._initialized = True
        log.info("Bot Lifecycle Manager initialized")
    
    def start(self) -> None:
        """Start the trading bot"""
        if self.status.state == BotState.RUNNING:
            log.warning("Bot is already running")
            return
        
        self.status.state = BotState.RUNNING
        self.status.start_time = datetime.utcnow()
        self.status.error_message = None
        log.info("🚀 Bot STARTED")
    
    def stop(self) -> None:
        """Stop the trading bot"""
        if self.status.state == BotState.STOPPED:
            log.warning("Bot is already stopped")
            return
        
        self.status.state = BotState.STOPPED
        self.status.stop_time = datetime.utcnow()
        log.info("🛑 Bot STOPPED")
    
    def pause(self) -> None:
        """Pause the trading bot (keep positions open)"""
        if self.status.state != BotState.RUNNING:
            log.warning("Bot is not running, cannot pause")
            return
        
        self.status.state = BotState.PAUSED
        self.status.pause_time = datetime.utcnow()
        log.info("⏸️  Bot PAUSED")
    
    def resume(self) -> None:
        """Resume the trading bot from paused state"""
        if self.status.state != BotState.PAUSED:
            log.warning("Bot is not paused, cannot resume")
            return
        
        self.status.state = BotState.RUNNING
        log.info("▶️  Bot RESUMED")
    
    def restart(self) -> None:
        """Restart the trading bot"""
        log.info("🔄 Bot RESTARTING...")
        self.stop()
        time.sleep(1)
        self.start()
    
    def set_error(self, error_message: str) -> None:
        """Set bot to error state"""
        self.status.state = BotState.ERROR
        self.status.error_message = error_message
        log.error(f"❌ Bot ERROR: {error_message}")
    
    def update_positions(self, active: int, pending: int) -> None:
        """Update position counts"""
        self.status.active_positions = active
        self.status.pending_orders = pending
    
    def get_status(self) -> BotStatus:
        """Get current bot status"""
        return self.status
    
    def is_running(self) -> bool:
        """Check if bot is running"""
        return self.status.state == BotState.RUNNING
    
    def is_paused(self) -> bool:
        """Check if bot is paused"""
        return self.status.state == BotState.PAUSED
    
    def is_stopped(self) -> bool:
        """Check if bot is stopped"""
        return self.status.state == BotState.STOPPED
    
    def can_trade(self) -> bool:
        """Check if bot can execute trades"""
        return self.status.state == BotState.RUNNING


# Global singleton instance
bot_lifecycle = BotLifecycleManager()


# Global singleton instance
bot_manager = BotLifecycleManager()

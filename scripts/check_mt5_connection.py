"""
Check MT5 connection and account balance.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger as log
from core.config import settings


def main():
    log.info("=" * 60)
    log.info("MT5 CONNECTION DIAGNOSTIC")
    log.info("=" * 60)
    
    try:
        import MetaTrader5 as mt5
        
        log.info("\n1. MT5 Library: ✓ Installed")
        
        # Try to initialize
        log.info("\n2. Attempting to connect to MT5...")
        log.info(f"   Login: {settings.mt5_login}")
        log.info(f"   Server: {settings.mt5_server}")
        
        if mt5.initialize(
            login=settings.mt5_login,
            password=settings.mt5_password,
            server=settings.mt5_server
        ):
            log.info("   ✓ MT5 Connected Successfully!")
            
            # Get account info
            account_info = mt5.account_info()
            
            if account_info:
                log.info("\n3. Account Information:")
                log.info(f"   Login: {account_info.login}")
                log.info(f"   Balance: ${account_info.balance:,.2f}")
                log.info(f"   Equity: ${account_info.equity:,.2f}")
                log.info(f"   Margin: ${account_info.margin:,.2f}")
                log.info(f"   Free Margin: ${account_info.margin_free:,.2f}")
                log.info(f"   Margin Level: {account_info.margin_level:.2f}%")
                log.info(f"   Currency: {account_info.currency}")
                log.info(f"   Server: {account_info.server}")
                log.info(f"   Leverage: 1:{account_info.leverage}")
                
                # Calculate risk limits
                balance = account_info.balance
                max_risk_6pct = balance * 0.06
                max_risk_10pct = balance * 0.10
                
                log.info("\n4. Risk Limits:")
                log.info(f"   6% of balance: ${max_risk_6pct:,.2f}")
                log.info(f"   10% of balance: ${max_risk_10pct:,.2f}")
                
                # Get open positions
                positions = mt5.positions_get()
                
                if positions:
                    log.info(f"\n5. Open Positions: {len(positions)}")
                    
                    total_risk = 0.0
                    for i, pos in enumerate(positions, 1):
                        # Calculate risk
                        if pos.type == mt5.POSITION_TYPE_BUY:
                            risk = pos.volume * (pos.price_open - pos.sl) * pos.point * pos.contract_size if pos.sl > 0 else 0
                        else:
                            risk = pos.volume * (pos.sl - pos.price_open) * pos.point * pos.contract_size if pos.sl > 0 else 0
                        
                        total_risk += abs(risk)
                        
                        log.info(f"\n   {i}. {pos.symbol}")
                        log.info(f"      Type: {'BUY' if pos.type == mt5.POSITION_TYPE_BUY else 'SELL'}")
                        log.info(f"      Volume: {pos.volume}")
                        log.info(f"      Entry: {pos.price_open}")
                        log.info(f"      Current: {pos.price_current}")
                        log.info(f"      SL: {pos.sl}")
                        log.info(f"      TP: {pos.tp}")
                        log.info(f"      Profit: ${pos.profit:,.2f}")
                        log.info(f"      Risk: ${abs(risk):,.2f}")
                    
                    risk_pct = (total_risk / balance) * 100
                    
                    log.info(f"\n6. Total Risk Analysis:")
                    log.info(f"   Combined Risk: ${total_risk:,.2f}")
                    log.info(f"   Risk %: {risk_pct:.2f}%")
                    
                    if risk_pct > 6.0:
                        log.warning(f"   ⚠️  OVER 6% LIMIT by {risk_pct - 6.0:.2f}%")
                        log.warning(f"   This is why new signals are rejected!")
                    else:
                        log.info(f"   ✓ Within 6% limit")
                        log.info(f"   Remaining capacity: {6.0 - risk_pct:.2f}%")
                else:
                    log.info("\n5. No open positions")
                
            else:
                log.error("   ✗ Could not get account info")
            
            mt5.shutdown()
            
        else:
            error = mt5.last_error()
            log.error(f"   ✗ MT5 Connection Failed!")
            log.error(f"   Error Code: {error[0]}")
            log.error(f"   Error Message: {error[1]}")
            log.info("\n   Possible reasons:")
            log.info("   1. MT5 terminal not running")
            log.info("   2. Wrong login/password/server")
            log.info("   3. MT5 terminal not allowing API connections")
            log.info("   4. Firewall blocking connection")
            
            log.info("\n   Solutions:")
            log.info("   1. Open MT5 terminal manually")
            log.info("   2. Check .env file has correct credentials")
            log.info("   3. Enable 'Allow DLL imports' in MT5 settings")
            
    except ImportError:
        log.error("✗ MetaTrader5 library not installed!")
        log.info("\n   Install with: pip install MetaTrader5")
    except Exception as e:
        log.error(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

"""
Test MT5 account fetching through the broker layer.
This verifies the fix for account balance retrieval.
"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger as log
from core.config import settings
from brokers.base import BrokerFactory, BrokerName


async def main():
    log.info("=" * 60)
    log.info("MT5 ACCOUNT FETCH TEST")
    log.info("=" * 60)
    
    factory = BrokerFactory(settings)
    broker = factory.get(BrokerName.MT5)
    
    log.info("\n1. Initial connection state: {}", "Connected" if broker.connected else "Not connected")
    
    # Test 1: Connect
    log.info("\n2. Attempting to connect...")
    success = await broker.connect()
    
    if success:
        log.info("   ✓ Connection successful")
    else:
        log.error("   ✗ Connection failed")
        return
    
    # Test 2: Get account info
    log.info("\n3. Fetching account info...")
    try:
        account = await broker.get_account()
        
        if account:
            log.info("   ✓ Account info retrieved:")
            log.info(f"      Broker: {account.broker}")
            log.info(f"      Balance: ${account.balance:,.2f}")
            log.info(f"      Equity: ${account.equity:,.2f}")
            log.info(f"      Margin: ${account.margin:,.2f}")
            log.info(f"      Free Margin: ${account.free_margin:,.2f}")
            log.info(f"      Margin %: {account.margin_pct:.2f}%")
            log.info(f"      Currency: {account.currency}")
            
            # Calculate risk limits
            max_risk_6pct = account.balance * 0.06
            max_risk_10pct = account.balance * 0.10
            
            log.info("\n4. Risk Limits:")
            log.info(f"   6% of balance: ${max_risk_6pct:,.2f}")
            log.info(f"   10% of balance: ${max_risk_10pct:,.2f}")
            
            # Check if this is a mock account
            if account.balance == 50000.0:
                log.warning("\n   ⚠️  This appears to be a MOCK account!")
                log.warning("   Real MT5 connection may have failed")
            else:
                log.info("\n   ✓ Real account data retrieved")
        else:
            log.error("   ✗ Account info is None")
            
    except Exception as e:
        log.error(f"   ✗ Error fetching account: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 3: Disconnect
    log.info("\n5. Disconnecting...")
    await broker.disconnect()
    log.info("   ✓ Disconnected")
    
    log.info("\n" + "=" * 60)
    log.info("TEST COMPLETE")
    log.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

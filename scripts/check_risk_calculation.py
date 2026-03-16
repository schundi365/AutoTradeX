"""
Check risk calculation and verify if it's correct.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from loguru import logger as log


async def main():
    log.info("=" * 60)
    log.info("RISK CALCULATION DIAGNOSTIC")
    log.info("=" * 60)
    
    try:
        async with httpx.AsyncClient() as client:
            # Get account info
            resp = await client.get("http://localhost:8000/api/status", timeout=10.0)
            
            if resp.status_code != 200:
                log.error("Failed to get status")
                return
            
            status = resp.json()
            balance = status.get('balance', 0)
            equity = status.get('equity', 0)
            
            log.info(f"\n📊 ACCOUNT INFO:")
            log.info(f"   Balance: ${balance:,.2f}")
            log.info(f"   Equity: ${equity:,.2f}")
            
            # Get open trades
            resp = await client.get("http://localhost:8000/api/trades/open", timeout=10.0)
            
            if resp.status_code != 200:
                log.error("Failed to get open trades")
                return
            
            trades = resp.json()
            
            log.info(f"\n📈 OPEN TRADES: {len(trades)}")
            
            # Calculate combined risk
            total_risk = 0.0
            
            for i, trade in enumerate(trades, 1):
                symbol = trade.get('symbol', 'N/A')
                direction = trade.get('direction', 'N/A')
                lot_size = trade.get('lot_size', 0)
                entry_price = trade.get('entry_price', 0)
                stop_loss = trade.get('stop_loss', 0)
                
                # Calculate point value (simplified)
                if 'XAU' in symbol or 'XAG' in symbol:
                    point_value = 100.0  # Metals
                elif 'JPY' in symbol:
                    point_value = 1000.0  # JPY pairs
                elif 'BTC' in symbol or 'ETH' in symbol:
                    point_value = 1.0  # Crypto
                else:
                    point_value = 100000.0  # Standard forex
                
                # Calculate risk for this trade
                sl_distance = abs(entry_price - stop_loss)
                trade_risk = lot_size * sl_distance * point_value
                total_risk += trade_risk
                
                log.info(f"\n   {i}. {symbol} {direction}")
                log.info(f"      Lot Size: {lot_size}")
                log.info(f"      Entry: {entry_price}")
                log.info(f"      Stop Loss: {stop_loss}")
                log.info(f"      SL Distance: {sl_distance:.5f}")
                log.info(f"      Point Value: {point_value}")
                log.info(f"      Trade Risk: ${trade_risk:,.2f}")
            
            # Calculate percentages
            log.info(f"\n" + "=" * 60)
            log.info("RISK ANALYSIS")
            log.info("=" * 60)
            
            log.info(f"\n💰 Combined Open Risk: ${total_risk:,.2f}")
            
            if balance > 0:
                risk_pct = (total_risk / balance) * 100
                log.info(f"📊 Risk as % of Balance: {risk_pct:.2f}%")
                
                # Get config
                resp = await client.get("http://localhost:8000/api/config", timeout=5.0)
                if resp.status_code == 200:
                    config = resp.json()
                    max_combined_risk_pct = config.get('risk', {}).get('max_combined_risk_pct', 6.0)
                    
                    max_allowed_risk = balance * (max_combined_risk_pct / 100)
                    
                    log.info(f"\n⚙️  Configuration:")
                    log.info(f"   Max Combined Risk: {max_combined_risk_pct}%")
                    log.info(f"   Max Allowed Risk: ${max_allowed_risk:,.2f}")
                    
                    remaining_capacity = max_allowed_risk - total_risk
                    
                    log.info(f"\n📉 Risk Status:")
                    if risk_pct > max_combined_risk_pct:
                        log.warning(f"   ⚠️  OVER LIMIT by {risk_pct - max_combined_risk_pct:.2f}%")
                        log.warning(f"   Over by: ${total_risk - max_allowed_risk:,.2f}")
                        log.info(f"\n   This is why new signals are being rejected!")
                        log.info(f"   Close some positions to free up risk capacity")
                    else:
                        log.info(f"   ✓ Within limit")
                        log.info(f"   Remaining capacity: ${remaining_capacity:,.2f}")
                        log.info(f"   Can add: {(max_combined_risk_pct - risk_pct):.2f}% more risk")
                
                # Show what would be needed for gold trade
                log.info(f"\n" + "=" * 60)
                log.info("GOLD TRADE ESTIMATE")
                log.info("=" * 60)
                
                # Typical gold trade
                gold_price = 5150.0  # Approximate
                gold_sl_distance = 30.0  # Typical SL distance
                gold_lot = 0.10  # Typical lot size
                gold_point_value = 100.0
                
                estimated_gold_risk = gold_lot * gold_sl_distance * gold_point_value
                
                log.info(f"\n   Estimated Gold Trade Risk: ${estimated_gold_risk:,.2f}")
                log.info(f"   Total Risk if Added: ${total_risk + estimated_gold_risk:,.2f}")
                
                if balance > 0:
                    new_risk_pct = ((total_risk + estimated_gold_risk) / balance) * 100
                    log.info(f"   New Risk %: {new_risk_pct:.2f}%")
                    
                    if new_risk_pct > max_combined_risk_pct:
                        log.warning(f"   ⚠️  Would exceed limit by {new_risk_pct - max_combined_risk_pct:.2f}%")
                    else:
                        log.info(f"   ✓ Would be within limit")
            
            # Recommendations
            log.info(f"\n" + "=" * 60)
            log.info("RECOMMENDATIONS")
            log.info("=" * 60)
            
            if risk_pct > max_combined_risk_pct:
                log.info(f"\n1. Close {int((risk_pct - max_combined_risk_pct) / 2) + 1}-2 positions to free up capacity")
                log.info(f"2. Or increase max_combined_risk_pct to {int(risk_pct) + 2}% (risky)")
                log.info(f"3. Or reduce lot sizes on future trades")
            else:
                log.info(f"\nYou have capacity for more trades!")
                log.info(f"The rejection was likely due to volume filter (G6), not risk limit")
                
    except Exception as e:
        log.error(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

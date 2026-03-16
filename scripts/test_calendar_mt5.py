import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import settings
from brokers.base import MT5Broker

async def main():
    print("Force-Testing MT5 Calendar Provider...")
    print(f"MT5 Account: {settings.mt5_login} on {settings.mt5_server}")
    
    # Manually instantiate MT5Broker to bypass 'paper' mode global check
    broker = MT5Broker(
        login=settings.mt5_login,
        password=settings.mt5_password,
        server=settings.mt5_server,
        path=settings.mt5_path
    )
    
    print("\nConnecting to MT5...")
    if not await broker.connect():
        print("FAILED to connect to MT5. Make sure the terminal is running and credentials are correct.")
        return

    print("\nFetching upcoming events from MT5 (48h)...")
    try:
        events = await broker.get_calendar_events(hours_ahead=48)
        print(f"\nFound {len(events)} events.")
        
        if events:
            # Sort by time
            events.sort(key=lambda x: x.scheduled)
            
            # Print top 15
            for e in events[:15]:
                print(f"[{e.scheduled.strftime('%Y-%m-%d %H:%M')}] {e.impact.value} | {e.currency} | {e.title}")
                if e.forecast:
                    print(f"    Forecast: {e.forecast} (Prev: {e.previous})")
            
            print("\n[SUCCESS] MT5 Calendar fetching verified!")
        else:
            print("\n[INFO] No events found. This might be normal if the market is closed or MT5 has no data.")
            
    except Exception as e:
        print(f"\n[FAILED] {str(e)}")
    finally:
        await broker.disconnect()

if __name__ == "__main__":
    asyncio.run(main())

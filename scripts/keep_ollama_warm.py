"""
Keep Ollama model loaded in memory for fast inference.

This script sends periodic lightweight requests to Ollama to prevent
the model from being unloaded from memory. This eliminates the 5-8 second
cold-start latency on first request after idle period.

Usage:
    python scripts/keep_ollama_warm.py

Run in background:
    Start-Process python -ArgumentList "scripts/keep_ollama_warm.py" -WindowStyle Hidden
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from loguru import logger as log

from core.config import settings


async def ping_ollama():
    """Send a minimal request to keep model loaded."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model": settings.ollama_model,
                    "prompt": "ping",
                    "stream": False,
                    "options": {
                        "num_predict": 1,  # Only generate 1 token
                        "temperature": 0.0
                    }
                }
            )
            
            if response.status_code == 200:
                return True
            else:
                log.warning(f"Ollama returned status {response.status_code}")
                return False
                
    except httpx.TimeoutException:
        log.warning("Ollama ping timeout (model may be loading)")
        return False
    except httpx.ConnectError:
        log.error("Cannot connect to Ollama - is it running?")
        return False
    except Exception as e:
        log.error(f"Ollama ping failed: {e}")
        return False


async def keep_warm_loop():
    """Main loop to keep model warm."""
    log.info(f"Starting Ollama keep-warm service for model: {settings.ollama_model}")
    log.info(f"Ollama URL: {settings.ollama_base_url}")
    log.info("Sending ping every 5 minutes to keep model loaded...")
    
    consecutive_failures = 0
    
    while True:
        success = await ping_ollama()
        
        if success:
            log.info("✓ Ollama model kept warm")
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            log.warning(f"✗ Keep-warm failed ({consecutive_failures} consecutive failures)")
            
            if consecutive_failures >= 3:
                log.error("Ollama appears to be down. Check if Ollama is running:")
                log.error("  ollama serve")
                log.error("  ollama ps")
        
        # Wait 5 minutes before next ping
        await asyncio.sleep(300)


def main():
    """Entry point."""
    try:
        asyncio.run(keep_warm_loop())
    except KeyboardInterrupt:
        log.info("Keep-warm service stopped by user")
    except Exception as e:
        log.error(f"Keep-warm service crashed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

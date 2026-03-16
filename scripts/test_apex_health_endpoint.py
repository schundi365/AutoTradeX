#!/usr/bin/env python3
"""Test apex health endpoint."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import httpx

async def test():
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8000/api/ai/apex-health", timeout=10.0)
            print(f"Status: {resp.status_code}")
            print(f"Response: {resp.json()}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())

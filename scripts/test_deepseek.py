import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import settings
from agents.graph import call_llm

async def main():
    print(f"Testing LLM Provider: {settings.llm_provider.value}")
    print(f"Model: {settings.llm_model}")
    
    if settings.llm_provider.value == "deepseek" and not settings.deepseek_api_key:
        print("ERROR: DEEPSEEK_API_KEY is not set in .env")
        return

    sys_prompt = "You are a helpful assistant. Reply with ONLY the word 'READY' if you can hear me."
    user_prompt = "Hello, are you functional?"
    
    print("\nCalling LLM...")
    try:
        resp = await call_llm(sys_prompt, user_prompt)
        print(f"\nResponse: {resp}")
        if "READY" in resp.upper():
            print("\n[SUCCESS] DeepSeek Integration SUCCESSFUL!")
        else:
            print("\n[WARNING] Unexpected response. Check your API key or model settings.")
    except Exception as e:
        print(f"\n[FAILED] {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())

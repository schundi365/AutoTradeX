#!/usr/bin/env python3
"""
Test script to verify Ollama connection and fine-tuned model
Run: python test_ollama_connection.py
"""
import asyncio
import httpx
from loguru import logger as log
from core.config import settings


async def test_ollama_connection():
    """Test if Ollama is running and model is available."""
    
    print("=" * 60)
    print("APEX Trading Bot - Ollama Connection Test")
    print("=" * 60)
    
    # Check configuration
    print(f"\n📋 Configuration:")
    print(f"   Ollama URL: {settings.ollama_base_url}")
    print(f"   Model Name: {settings.ollama_model}")
    
    # Test 1: Check if Ollama is running
    print(f"\n🔍 Test 1: Checking Ollama server...")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags", timeout=5.0)
            if resp.status_code == 200:
                print(f"   ✅ Ollama server is running")
                models = resp.json().get("models", [])
                print(f"   📦 Available models: {len(models)}")
                for model in models:
                    model_name = model.get("name", "unknown")
                    size = model.get("size", 0) / (1024**3)  # Convert to GB
                    print(f"      - {model_name} ({size:.2f} GB)")
            else:
                print(f"   ❌ Ollama server returned status {resp.status_code}")
                return False
    except httpx.ConnectError:
        print(f"   ❌ Cannot connect to Ollama at {settings.ollama_base_url}")
        print(f"   💡 Make sure Ollama is running: ollama serve")
        return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False
    
    # Test 2: Check if your fine-tuned model exists
    print(f"\n🔍 Test 2: Checking for model '{settings.ollama_model}'...")
    model_found = False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags", timeout=5.0)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                for model in models:
                    if settings.ollama_model in model.get("name", ""):
                        model_found = True
                        print(f"   ✅ Model '{settings.ollama_model}' found!")
                        break
                
                if not model_found:
                    print(f"   ❌ Model '{settings.ollama_model}' not found")
                    print(f"   💡 Available models:")
                    for model in models:
                        print(f"      - {model.get('name', 'unknown')}")
                    print(f"\n   💡 To load your model:")
                    print(f"      ollama run {settings.ollama_model}")
                    return False
    except Exception as e:
        print(f"   ❌ Error checking model: {e}")
        return False
    
    # Test 3: Test inference with your model
    print(f"\n🔍 Test 3: Testing inference with '{settings.ollama_model}'...")
    try:
        test_prompt = """You are APEX, a professional trading analyst. Analyze this market condition:

Symbol: XAUUSD (Gold)
Current Price: 2650.50
RSI: 68
MACD: Bullish crossover
Trend: Uptrend on H1, H4
Volume: Above average

Provide a brief trading signal (BUY/SELL/HOLD) with reasoning."""

        payload = {
            "model": settings.ollama_model,
            "prompt": test_prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 256
            }
        }
        
        print(f"   ⏳ Sending test prompt...")
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=60.0)) as client:
            resp = await asyncio.wait_for(
                client.post(f"{settings.ollama_base_url}/api/generate", json=payload),
                timeout=60.0
            )
            
            if resp.status_code == 200:
                result = resp.json()
                response = result.get("response", "").strip()
                eval_count = result.get("eval_count", 0)
                eval_duration = result.get("eval_duration", 0) / 1e9  # Convert to seconds
                tokens_per_sec = eval_count / eval_duration if eval_duration > 0 else 0
                
                print(f"   ✅ Inference successful!")
                print(f"   📊 Performance:")
                print(f"      - Tokens generated: {eval_count}")
                print(f"      - Time taken: {eval_duration:.2f}s")
                print(f"      - Speed: {tokens_per_sec:.1f} tokens/sec")
                print(f"\n   📝 Model Response:")
                print(f"   {'-' * 56}")
                # Print first 300 chars of response
                preview = response[:300] + "..." if len(response) > 300 else response
                for line in preview.split('\n'):
                    print(f"   {line}")
                print(f"   {'-' * 56}")
                
                # Check if response looks reasonable
                if len(response) < 20:
                    print(f"   ⚠️  Warning: Response seems too short")
                    return False
                    
                return True
            else:
                print(f"   ❌ Inference failed with status {resp.status_code}")
                print(f"   Response: {resp.text}")
                return False
                
    except asyncio.TimeoutError:
        print(f"   ❌ Inference timeout (60s)")
        print(f"   💡 Your model might be too slow or not loaded in memory")
        print(f"   💡 Try preloading: ollama run {settings.ollama_model}")
        print(f"   💡 Or increase timeout in llm/client.py: OLLAMA_TIMEOUT = 15")
        return False
    except Exception as e:
        print(f"   ❌ Inference error: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"   📋 Full error:")
        traceback.print_exc()
        return False


async def test_llm_client():
    """Test the actual LLM client used by the bot."""
    print(f"\n🔍 Test 4: Testing APEX LLM Client...")
    
    try:
        from llm.client import call_llm
        
        result = await call_llm(
            system="You are APEX trading analyst. Be concise.",
            user="What's your primary function?",
            max_tokens=100,
            agent="test"
        )
        
        if result:
            print(f"   ✅ LLM Client working!")
            print(f"   📝 Response: {result[:150]}...")
            return True
        else:
            print(f"   ❌ LLM Client returned None")
            print(f"   💡 Check logs above for which tier was used")
            return False
            
    except Exception as e:
        print(f"   ❌ LLM Client error: {e}")
        return False


async def main():
    """Run all tests."""
    
    # Run tests
    test1 = await test_ollama_connection()
    
    if test1:
        test2 = await test_llm_client()
    else:
        test2 = False
    
    # Summary
    print(f"\n{'=' * 60}")
    print(f"Test Summary:")
    print(f"{'=' * 60}")
    print(f"   Ollama Connection: {'✅ PASS' if test1 else '❌ FAIL'}")
    print(f"   LLM Client:        {'✅ PASS' if test2 else '❌ FAIL'}")
    
    if test1 and test2:
        print(f"\n🎉 All tests passed! Your fine-tuned model is ready.")
        print(f"\n💡 Next steps:")
        print(f"   1. Start the bot: python main.py")
        print(f"   2. Monitor logs for: [agent] 🤖 LLM Tier 1 (Ollama/{settings.ollama_model}) ✓")
        print(f"   3. Fallback tiers will only be used if Ollama fails")
    else:
        print(f"\n❌ Some tests failed. Please fix the issues above.")
        print(f"\n💡 Common fixes:")
        print(f"   - Start Ollama: ollama serve")
        print(f"   - Load model: ollama run {settings.ollama_model}")
        print(f"   - Check .env file has correct OLLAMA_BASE_URL and OLLAMA_MODEL")
    
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())

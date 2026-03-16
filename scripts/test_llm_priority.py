import asyncio
import json
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

# Mocking settings before import to avoid errors
import os
os.environ["LLM_PRIMARY"] = "local"
os.environ["OLLAMA_MODEL"] = "apex-trader"

from core.config import settings
from agents.graph import call_llm

class TestLLMPriority(unittest.IsolatedAsyncioTestCase):
    async def test_call_llm_local_priority(self):
        print("\nTesting LLM Priority...")
        
        # We'll mock the internal provider functions by mocking the network calls they make
        # For 'local', it makes a POST request to ollama_base_url
        
        # 1. Test is_finetuned=True (Should hit local first regardless of primary)
        with patch("httpx.AsyncClient.post") as mock_post:
            # Mock success for local
            mock_post.return_value = MagicMock(status_code=200)
            mock_post.return_value.json.return_value = {"response": "GO"}
            
            print("Checking is_finetuned=True prioritization...")
            resp = await call_llm("System Prompt", "User Input", is_finetuned=True)
            
            self.assertEqual(resp, "GO")
            self.assertTrue(mock_post.called)
            # Verify it hit the local Ollama URL
            self.assertIn("11434/api/generate", mock_post.call_args[0][0])
            print("SUCCESS: Local model prioritized for fine-tuned call.")

    async def test_fallback_sequence(self):
        print("\nChecking fallback sequence when local fails...")
        
        # Mock local failure
        with patch("httpx.AsyncClient.post") as mock_local:
            mock_local.side_effect = Exception("Ollama Down")
            
            # Mock OpenAI (Groq and DeepSeek)
            with patch("openai.AsyncOpenAI") as mock_openai_class:
                mock_groq_client = MagicMock()
                mock_deepseek_client = MagicMock()
                
                # Groq returns error, DeepSeek returns success
                mock_groq_client.chat.completions.create = AsyncMock(side_effect=Exception("Groq Fail"))
                mock_deepseek_client.chat.completions.create = AsyncMock(return_value=MagicMock(
                    choices=[MagicMock(message=MagicMock(content="DEEPSEEK_RESPONSE"))]
                ))
                
                # AsyncOpenAI() called twice: once for Groq, once for DeepSeek
                mock_openai_class.side_effect = [mock_groq_client, mock_deepseek_client]
                
                # Ensure settings have keys to trigger attempts
                settings.groq_api_key = "test_groq"
                settings.deepseek_api_key = "test_deepseek"
                
                # Mock Anthropic to avoid hitting the real API if something goes wrong
                with patch("anthropic.AsyncAnthropic") as mock_anthropic_class:
                    mock_anthropic_class.return_value.messages.create = AsyncMock(side_effect=Exception("Claude Fail"))
                    
                    resp = await call_llm("System", "User", is_finetuned=True)
                    
                    self.assertEqual(resp, "DEEPSEEK_RESPONSE")
                    print("SUCCESS: Fallback logic sequences correctly (Local -> Groq -> DeepSeek).")

if __name__ == "__main__":
    unittest.main()

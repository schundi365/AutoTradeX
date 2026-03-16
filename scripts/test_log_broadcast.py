import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime

# Mock settings and logger before importing core components
import os
os.environ["LOG_LEVEL"] = "INFO"

from core.logger import _ws_sink

class TestLogBroadcast(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Create a mock record structure like loguru provides
        self.base_record = {
            "time": datetime.utcnow(),
            "name": "test_module",
            "extra": {"agent": "TEST_AGENT"},
            "level": MagicMock(name="INFO")
        }
        self.base_record["level"].name = "INFO"

    def test_signal_categorization(self):
        print("\nTesting Signal Categorization...")
        mock_msg = MagicMock()
        mock_msg.record = self.base_record.copy()
        mock_msg.record["message"] = "[ORCHESTRATOR] REJECTED AAPL signal due to score"
        
        with patch("core.logger._ws_clients", {MagicMock()}) as clients:
            ws = list(clients)[0]
            ws.send_text = MagicMock()
            
            # We call the sink directly
            _ws_sink(mock_msg)
            
            # Extract the payload sent to ws.send_text
            # Note: _ws_sink uses ensure_future or run_coroutine_threadsafe
            # For this test, we just want to verify the 'level' field in the payload
            # But wait, _ws_sink is sync and starts an async task. 
            # We can capture the payload by patching json.dumps
            
            with patch("json.dumps") as mock_json:
                _ws_sink(mock_msg)
                args, _ = mock_json.call_args
                payload = args[0]
                self.assertEqual(payload["level"], "SIGNAL")
                print("SUCCESS: [ORCHESTRATOR] REJECTED categorized as SIGNAL")

    def test_trade_categorization(self):
        print("\nTesting Trade Categorization...")
        mock_msg = MagicMock()
        mock_msg.record = self.base_record.copy()
        mock_msg.record["message"] = "[ORCHESTRATOR] APPROVED BUY GOLD - high conviction"
        
        with patch("json.dumps") as mock_json:
            _ws_sink(mock_msg)
            payload = mock_json.call_args[0][0]
            self.assertEqual(payload["level"], "TRADE")
            print("SUCCESS: [ORCHESTRATOR] APPROVED categorized as TRADE")

    def test_error_categorization(self):
        print("\nTesting Error Categorization...")
        mock_msg = MagicMock()
        mock_msg.record = self.base_record.copy()
        mock_msg.record["level"].name = "ERROR"
        mock_msg.record["message"] = "MT5 connection failed"
        
        with patch("json.dumps") as mock_json:
            _ws_sink(mock_msg)
            payload = mock_json.call_args[0][0]
            self.assertEqual(payload["level"], "WARN")
            print("SUCCESS: ERROR level categorized as WARN (for ERRORS filter)")

    def test_ai_categorization(self):
        print("\nTesting AI Categorization...")
        mock_msg = MagicMock()
        mock_msg.record = self.base_record.copy()
        mock_msg.record["message"] = "🧠 Fine-tuning started on Kaggle"
        
        with patch("json.dumps") as mock_json:
            _ws_sink(mock_msg)
            payload = mock_json.call_args[0][0]
            self.assertEqual(payload["level"], "AI")
            print("SUCCESS: AI emoji categorized as AI")

if __name__ == "__main__":
    unittest.main()

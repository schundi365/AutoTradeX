import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.orchestrator import TrainingOrchestrator

def test_orchestrator_initialization():
    orchestrator = TrainingOrchestrator()
    print("[OK] Orchestrator initialized successfully.")
    return orchestrator

def test_orchestrator_mock_run():
    orchestrator = TrainingOrchestrator()
    
    # Mock the individual steps so we don't actually run them
    orchestrator._step_collect_historical = MagicMock()
    orchestrator._step_collect_macro = MagicMock()
    orchestrator._step_prepare_data = MagicMock()
    orchestrator._step_finetune = MagicMock()
    orchestrator._step_convert_and_reload = MagicMock()
    
    print("[START] Triggering mock pipeline run...")
    orchestrator.run_full_llm_pipeline()
    
    # Give it a second to start the thread
    time.sleep(1)
    
    if orchestrator._is_running:
        print("[OK] Pipeline is running in background thread.")
    
    # Wait for execution to finish (since it's mocked, it should be fast)
    max_wait = 5
    start_time = time.time()
    while orchestrator._is_running and (time.time() - start_time) < max_wait:
        time.sleep(0.5)
        
    if not orchestrator._is_running:
        print("[OK] Pipeline execution finished.")
        # Verify all mocks were called
        orchestrator._step_collect_historical.assert_called_once()
        orchestrator._step_collect_macro.assert_called_once()
        orchestrator._step_prepare_data.assert_called_once()
        orchestrator._step_finetune.assert_called_once()
        orchestrator._step_convert_and_reload.assert_called_once()
        print("[OK] All pipeline steps were invoked in the background.")
    else:
        print("[FAIL] Pipeline timed out or failed to stop.")
        sys.exit(1)

if __name__ == "__main__":
    print("--- APEX Orchestrator Smoke Test ---")
    test_orchestrator_initialization()
    test_orchestrator_mock_run()
    print("--- Test Passed ---")

from __future__ import annotations
import sys
import uuid
import threading
import asyncio
from datetime import datetime
from pathlib import Path
from core.config import settings
from core.logger import get_agent_logger

log = get_agent_logger("ORCHESTRATOR")

class TrainingOrchestrator:
    """
    Orchestrates the full LLM training pipeline:
    Collection -> Preparation -> Fine-tuning -> Conversion -> Reload.
    """
    def __init__(self):
        self._is_running = False
        self._current_job_id = None
        # This will be injected by server.py to track jobs
        self.jobs_registry = {}

    def run_full_llm_pipeline(self):
        """
        Main entry point for scheduled or manual full pipeline runs.
        Runs in a background thread to avoid blocking the server.
        """
        if self._is_running:
            log.warning("Training pipeline already running. Skipping request.")
            return
        
        thread = threading.Thread(target=self._execute_pipeline, daemon=True)
        thread.start()

    def _execute_pipeline(self):
        self._is_running = True
        job_id = f"full_{uuid.uuid4().hex[:8]}"
        self._current_job_id = job_id
        
        log.info("[TRAINING] Full LLM Pipeline started — Job: {}", job_id)
        
        try:
            # 1. Historical Data Collection
            self._step_collect_historical(job_id)
            
            # 2. Macro Data Collection
            self._step_collect_macro(job_id)
            
            # 3. Export/Prepare Training Data
            self._step_prepare_data(job_id)
            
            # 4. Fine-Tuning (Remote or Local)
            self._step_finetune(job_id)
            
            # 5. Conversion & Ollama Reload
            self._step_convert_and_reload(job_id)
            
            log.info("[TRAINING] Full LLM Pipeline complete — Job: {}", job_id)
            
        except Exception as e:
            log.error("[TRAINING] Pipeline failed at job {}: {}", job_id, e)
        finally:
            self._is_running = False
            self._current_job_id = None

    def _step_collect_historical(self, job_id):
        log.info("[HIST] Step 1/5: Collecting historical OHLCV data...")
        from scripts.collect_historical_data import collect_yfinance, collect_ccxt, load_csv_to_duckdb
        t = settings.training
        
        total = collect_yfinance(
            start=t.historical_start_date,
            interval=t.yfinance_timeframe,
            out_dir=t.raw_data_dir,
            symbols=t.yfinance_symbols,
        )
        total += collect_ccxt(
            timeframe=t.ccxt_timeframe,
            start=t.ccxt_start_date,
            out_dir=t.raw_data_dir,
        )
        load_csv_to_duckdb(csv_dir=t.raw_data_dir, db_path=t.duckdb_path)
        log.info("[HIST] Step complete: {:,} bars synced", total)

    def _step_collect_macro(self, job_id):
        log.info("[MACRO] Step 2/5: Collecting macro indicators and sentiment...")
        from scripts.collect_macro_data import collect_fred, collect_cot, load_macro_to_duckdb
        t = settings.training
        
        if t.fred_api_key:
            collect_fred(
                api_key=t.fred_api_key,
                start=t.historical_start_date,
                series=t.fred_series,
                out_dir=t.macro_data_dir,
            )
        collect_cot(out_dir=t.macro_data_dir)
        load_macro_to_duckdb(db_path=t.duckdb_path, macro_dir=t.macro_data_dir)

    def _step_prepare_data(self, job_id):
        log.info("[EXPORT] Step 3/5: Preparing training dataset (JSONL)...")
        from scripts.prepare_training_data import export_training_data
        t = settings.training
        
        out_path = export_training_data(
            db_path=t.duckdb_path,
            min_examples=t.min_training_examples,
            include_synthetic=t.include_synthetic,
            out_dir=t.training_data_dir,
        )
        if not out_path:
            raise RuntimeError("Data preparation failed or insufficient samples.")
        log.info("[EXPORT] Training data ready: {}", out_path)

    def _step_finetune(self, job_id):
        t = settings.training
        # If Kaggle credentials are set, prefer Kaggle to save local GPU
        if t.kaggle_username and t.kaggle_api_key:
            log.info("[KAGGLE] Step 4/5: Starting remote fine-tuning on Kaggle...")
            from scripts.run_remote_training import run_on_kaggle
            
            # Prepare config dict for run_on_kaggle
            config = {
                "username":              t.kaggle_username,
                "api_key":               t.kaggle_api_key,
                "dataset_name":          t.kaggle_dataset_name,
                "kernel_name":           t.kaggle_kernel_name,
                "gpu_type":              t.kaggle_gpu_type,
                "training_data_dir":     t.training_data_dir,
                "model_output_dir":      t.model_output_dir,
                "base_model":            t.base_model,
                "max_seq_length":        t.max_seq_length,
                "lora_rank":             t.lora_rank,
                "lora_alpha":            t.lora_alpha,
                "num_epochs":            t.num_epochs,
                "batch_size":            t.batch_size,
                "gradient_accumulation": t.gradient_accumulation,
                "learning_rate":         t.learning_rate,
                "quant_type":            t.quant_type,
            }
            
            result = run_on_kaggle(config)
            if result["status"] == "error":
                raise RuntimeError(f"Kaggle fine-tuning failed: {result['error']}")
            
            log.info("[KAGGLE] Remote training complete. Model saved to {}", t.model_output_dir)
        else:
            log.info("[FT] Step 4/5: Starting local fine-tuning (Unsloth)...")
            from scripts.fine_tune import run_finetuning
            data_path = str(Path(t.training_data_dir) / "apex_training_latest.jsonl")
            run_finetuning(
                data_path=data_path,
                output_dir=t.model_output_dir,
                base_model=t.base_model,
                num_epochs=t.num_epochs,
                batch_size=t.batch_size,
            )

    def _step_convert_and_reload(self, job_id):
        log.info("[CONVERT] Step 5/5: Converting model and reloading Ollama...")
        from scripts.conversion import convert_to_gguf, write_modelfile, load_into_ollama, find_model_paths
        t = settings.training
        
        merged_path, _ = find_model_paths(t.model_output_dir)
        if not merged_path:
            raise RuntimeError(f"No merged model weights found in {t.model_output_dir}")
            
        success = convert_to_gguf(
            model_dir=merged_path,
            output_path=Path(t.gguf_output),
            quant_type=t.quant_type,
        )
        if success:
            mf = write_modelfile(Path(t.gguf_output))
            load_into_ollama(mf, model_name=t.ollama_model_name)
            log.info("[CONVERT] Model successfully reloaded in Ollama: {}", t.ollama_model_name)
        else:
            raise RuntimeError("GGUF Conversion failed.")

orchestrator = TrainingOrchestrator()

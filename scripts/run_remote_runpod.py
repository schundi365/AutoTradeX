"""
APEX Bot — RunPod Serverless Fine-Tuning Orchestration

Automates the full RunPod remote training pipeline:
  1. Submit job to RunPod Serverless endpoint (training data embedded as base64)
  2. Poll job status until COMPLETED / FAILED (up to 4 hours)
  3. Download GGUF from the presigned URL returned by the handler
  4. Place GGUF in the configured model output directory

Prerequisites:
    pip install requests
    RunPod Serverless endpoint running the apex-runpod Docker image.
    Set RUNPOD_API_KEY + RUNPOD_ENDPOINT_ID in Training Config or .env.

Usage:
    python scripts/run_remote_runpod.py
    python scripts/run_remote_runpod.py --api-key rpk_xxx --endpoint abc123def
"""
from __future__ import annotations
import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import settings as _settings

# RunPod Serverless REST API base
_RUNPOD_BASE = "https://api.runpod.io/v2"

# Job status values returned by RunPod
_TERMINAL_OK  = {"COMPLETED"}
_TERMINAL_ERR = {"FAILED", "CANCELLED", "TIMED_OUT"}
_RUNNING      = {"IN_QUEUE", "IN_PROGRESS"}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Submit job
# ─────────────────────────────────────────────────────────────────────────────

def submit_job(
    endpoint_id: str,
    api_key: str,
    training_jsonl_path: str | Path,
    config: dict,
) -> str:
    """Submit a fine-tuning job to the RunPod Serverless endpoint.

    Embeds the training JSONL as base64 in the job payload.
    Returns the RunPod job ID string.
    """
    import urllib.request

    jsonl_bytes = Path(training_jsonl_path).read_bytes()
    data_b64 = base64.b64encode(jsonl_bytes).decode("ascii")
    size_kb = len(jsonl_bytes) // 1024
    print(f"  [RunPod] Submitting job — data: {size_kb} KB, config: {list(config.keys())}")

    payload = json.dumps({
        "input": {
            "training_data_b64": data_b64,
            "config": config,
        }
    }).encode("utf-8")

    url = f"{_RUNPOD_BASE}/{endpoint_id}/run"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        },
        method="POST",
    )
    resp_bytes = urllib.request.urlopen(req, timeout=60).read()
    resp = json.loads(resp_bytes)
    job_id = resp.get("id")
    if not job_id:
        raise RuntimeError(f"RunPod submit failed — no job ID in response: {resp}")
    print(f"  [RunPod] Job submitted: {job_id}  status: {resp.get('status', '?')}")
    return job_id


# ─────────────────────────────────────────────────────────────────────────────
# 2. Poll status
# ─────────────────────────────────────────────────────────────────────────────

def poll_job(
    endpoint_id: str,
    api_key: str,
    job_id: str,
    timeout_hours: float = 4.0,
    poll_interval: int = 30,
) -> dict:
    """Poll RunPod until the job reaches a terminal state.

    Returns a dict with keys: status, output (if COMPLETED), error (if FAILED).
    """
    import urllib.request

    deadline = time.time() + timeout_hours * 3600
    url = f"{_RUNPOD_BASE}/{endpoint_id}/status/{job_id}"
    headers = {"Authorization": f"Bearer {api_key}"}

    print(f"  [RunPod] Polling job {job_id} (timeout: {timeout_hours}h, interval: {poll_interval}s)")
    elapsed_min = 0

    while time.time() < deadline:
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
        except Exception as e:
            print(f"  [RunPod] Poll error: {e} — retrying in {poll_interval}s")
            time.sleep(poll_interval)
            continue

        status = resp.get("status", "UNKNOWN")
        elapsed_min = int((time.time() - (deadline - timeout_hours * 3600)) / 60)

        if status in _TERMINAL_OK:
            output = resp.get("output", {})
            print(f"  [RunPod] COMPLETED in ~{elapsed_min}m")
            return {"status": "complete", "output": output, "elapsed_min": elapsed_min}

        if status in _TERMINAL_ERR:
            error = resp.get("error") or resp.get("output", {}).get("error", status)
            print(f"  [RunPod] FAILED after {elapsed_min}m: {error}")
            return {"status": "error", "error": error, "elapsed_min": elapsed_min}

        print(f"  [RunPod] {status} — {elapsed_min}m elapsed, waiting {poll_interval}s...")
        time.sleep(poll_interval)

    return {"status": "error", "error": f"Timed out after {timeout_hours}h"}


# ─────────────────────────────────────────────────────────────────────────────
# 3. Download GGUF
# ─────────────────────────────────────────────────────────────────────────────

def download_gguf(url: str, dest_path: str | Path) -> str:
    """Download GGUF from presigned URL to dest_path.

    Uses chunked streaming so large files (4-5 GB) don't exhaust memory.
    Returns the path as a string on success.
    """
    import urllib.request

    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    print(f"  [RunPod] Downloading GGUF → {dest}")
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=3600) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunk = 8 * 1024 * 1024  # 8 MB chunks
        with open(dest, "wb") as f:
            while True:
                block = resp.read(chunk)
                if not block:
                    break
                f.write(block)
                downloaded += len(block)
                if total:
                    pct = downloaded / total * 100
                    print(f"\r  [RunPod] {downloaded / 1e9:.2f} / {total / 1e9:.2f} GB ({pct:.0f}%)",
                          end="", flush=True)
        print()  # newline after progress

    size_gb = dest.stat().st_size / 1e9
    print(f"  [RunPod] Download complete: {dest} ({size_gb:.2f} GB)")
    return str(dest)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Full pipeline
# ─────────────────────────────────────────────────────────────────────────────

def run_on_runpod(config: dict) -> dict:
    """Run the complete RunPod remote training pipeline.

    config keys: api_key, endpoint_id, training_data_dir, model_output_dir,
                 base_model, lora_rank, lora_alpha, num_epochs, batch_size,
                 gradient_accumulation, learning_rate, max_seq_length, quant_type.
    Returns: {status, gguf_path, adapter_url, train_loss, duration_seconds, error}
    """
    t0 = time.time()

    api_key     = config.get("api_key",      "")
    endpoint_id = config.get("endpoint_id",  "")
    output_dir  = config.get("model_output_dir", "models/apex_trading_model")

    if not api_key:
        return {"status": "error", "error": "RunPod API key not set — configure in Training Config"}
    if not endpoint_id:
        return {"status": "error", "error": "RunPod Endpoint ID not set — configure in Training Config"}

    training_jsonl = Path(config.get("training_data_dir", "training_data")) / "apex_training_latest.jsonl"
    if not training_jsonl.exists():
        return {
            "status": "error",
            "error":  f"Training data not found: {training_jsonl}. Run Export (Step 3) first.",
        }

    print(f"\n{'='*60}")
    print("APEX Remote Training — RunPod Serverless GPU")
    print(f"  Endpoint: {endpoint_id}")
    print(f"  Data    : {training_jsonl} ({training_jsonl.stat().st_size // 1024} KB)")
    print(f"  Model   : {config.get('base_model', '?')}")
    print(f"{'='*60}\n")

    # Hyperparams to send to the handler
    job_config = {
        "base_model":            config.get("base_model",            "unsloth/llama-3.1-8b-bnb-4bit"),
        "max_seq_length":        config.get("max_seq_length",        2048),
        "lora_rank":             config.get("lora_rank",             16),
        "lora_alpha":            config.get("lora_alpha",            16),
        "num_epochs":            config.get("num_epochs",            3),
        "batch_size":            config.get("batch_size",            2),
        "gradient_accumulation": config.get("gradient_accumulation", 4),
        "learning_rate":         config.get("learning_rate",         2e-4),
        "quant_type":            config.get("quant_type",            "q4_k_m"),
    }

    # Step 1 — Submit
    try:
        job_id = submit_job(endpoint_id, api_key, training_jsonl, job_config)
    except Exception as e:
        err_msg = str(e)
        if "403" in err_msg:
            print("\n    [RUNPOD] ERROR 403: Forbidden.")
            print("      This usually means your RUNPOD_API_KEY is invalid, expired,")
            print("      or does not have permission for the specified Endpoint ID.")
            print("    [TIP] Double-check your API Key and Endpoint ID in the RunPod dashboard.")
            return {
                "status": "error",
                "error": f"RunPod 403 Forbidden: Check your API Key and Endpoint ID. Details: {e}"
            }
        return {"status": "error", "error": f"Job submit failed: {e}"}

    # Step 2 — Poll
    try:
        poll_result = poll_job(endpoint_id, api_key, job_id)
    except Exception as e:
        return {"status": "error", "error": f"Polling failed: {e}", "job_id": job_id}

    if poll_result["status"] != "complete":
        return {
            "status":           "error",
            "error":            poll_result.get("error", "Job did not complete"),
            "job_id":           job_id,
            "duration_seconds": int(time.time() - t0),
        }

    output = poll_result.get("output", {})
    handler_status = output.get("status", "unknown")
    print(f"  [RunPod] Handler status: {handler_status}")
    if output.get("error"):
        print(f"  [RunPod] Handler error: {output['error']}")

    gguf_url    = output.get("gguf_url")
    adapter_url = output.get("adapter_url")
    train_loss  = output.get("train_loss")

    # Step 3 — Download GGUF
    gguf_path = None
    if gguf_url:
        gguf_dest = Path(output_dir) / "apex_trading_model.gguf"
        try:
            gguf_path = download_gguf(gguf_url, gguf_dest)
        except Exception as e:
            print(f"  [RunPod] GGUF download failed: {e}")
    else:
        print("  [RunPod] No GGUF URL in output — handler may not have produced one.")
        if adapter_url:
            print(f"  [RunPod] LoRA adapter available: {adapter_url}")

    duration = int(time.time() - t0)
    print(f"\n{'='*60}")
    print(f"RunPod training complete in {duration // 60}m {duration % 60}s")
    print(f"  GGUF     : {gguf_path or 'not downloaded'}")
    print(f"  Loss     : {train_loss}")
    print(f"{'='*60}")
    if gguf_path:
        print("Next: Click Convert → GGUF (Step 5) — GGUF already downloaded, will skip conversion")
    else:
        print("Next: Click Convert → GGUF (Step 5) — will attempt local merge")

    return {
        "status":           "done" if (gguf_path or adapter_url) else "error",
        "gguf_path":        gguf_path,
        "adapter_url":      adapter_url,
        "model_dir":        output_dir,
        "train_loss":       train_loss,
        "job_id":           job_id,
        "duration_seconds": duration,
        "error":            None if (gguf_path or adapter_url) else "No outputs available",
    }


# ─────────────────────────────────────────────────────────────────────────────

def main():
    tr = _settings.training
    parser = argparse.ArgumentParser(description="APEX RunPod remote fine-tuning")
    parser.add_argument("--api-key",    default=None, help=f"RunPod API key (default: RUNPOD_API_KEY)")
    parser.add_argument("--endpoint",  default=None, help=f"RunPod endpoint ID (default: RUNPOD_ENDPOINT_ID)")
    parser.add_argument("--data",      default=None, help=f"Training data dir (default: {tr.training_data_dir})")
    parser.add_argument("--out",       default=None, help=f"Model output dir (default: {tr.model_output_dir})")
    args = parser.parse_args()

    result = run_on_runpod({
        "api_key":               args.api_key  or tr.runpod_api_key,
        "endpoint_id":           args.endpoint or tr.runpod_endpoint_id,
        "training_data_dir":     args.data     or tr.training_data_dir,
        "model_output_dir":      args.out      or tr.model_output_dir,
        "base_model":            tr.base_model,
        "max_seq_length":        tr.max_seq_length,
        "lora_rank":             tr.lora_rank,
        "lora_alpha":            tr.lora_alpha,
        "num_epochs":            tr.num_epochs,
        "batch_size":            tr.batch_size,
        "gradient_accumulation": tr.gradient_accumulation,
        "learning_rate":         tr.learning_rate,
        "quant_type":            tr.quant_type,
    })

    if result["status"] == "done":
        print("\nDone! Run Convert → GGUF (Step 5) to register with Ollama.")
    else:
        print(f"\nFailed: {result.get('error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()

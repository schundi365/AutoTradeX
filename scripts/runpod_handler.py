"""
APEX Bot — RunPod Serverless Handler
Runs inside the RunPod GPU container (built from Dockerfile.runpod).

Input payload (JSON):
    {
        "training_data_b64": "<base64-encoded apex_training_latest.jsonl>",
        "config": {
            "base_model":    "unsloth/llama-3.1-8b-bnb-4bit",
            "max_seq_length": 2048,
            "lora_rank": 16,
            "lora_alpha": 16,
            "num_epochs": 3,
            "batch_size": 2,
            "gradient_accumulation": 4,
            "learning_rate": 2e-4,
            "quant_type": "q4_k_m"
        }
    }

Output (returned to caller via RunPod job status):
    {
        "status": "done",
        "gguf_url": "<presigned S3 URL valid ~1h>",
        "adapter_url": "<presigned S3 URL>",
        "gguf_size_gb": 4.5,
        "train_loss": 0.123,
        "train_runtime_s": 850
    }

The GGUF and LoRA adapter files are uploaded via runpod.serverless.utils.rp_upload()
which stores them in RunPod's managed S3 bucket and returns a time-limited presigned URL.
The caller downloads the GGUF from that URL — no cloud storage setup required.
"""
from __future__ import annotations
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import runpod

# ── Working directories inside the container ──────────────────────────────────
WORK_DIR    = "/tmp/apex_work"
TRAIN_FILE  = f"{WORK_DIR}/apex_training_latest.jsonl"
OUTPUT_DIR  = f"{WORK_DIR}/apex_trading_model"
MERGED_DIR  = f"{WORK_DIR}/apex_trading_model_merged"
GGUF_OUTPUT = f"{WORK_DIR}/apex_trading_model.gguf"

# Path to the fine-tuning kernel (baked into the Docker image)
KERNEL_SCRIPT = "/finetune_kernel.py"


def _install_deps():
    """Install fine-tuning dependencies if not already present."""
    pkgs = ["trl>=0.8", "transformers>=4.40", "accelerate>=0.27",
            "bitsandbytes>=0.43", "datasets>=2.18", "peft>=0.10",
            "sentencepiece", "protobuf"]
    print("[Setup] Installing/verifying fine-tuning dependencies...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "--upgrade"] + pkgs,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"[Setup] pip WARNING (rc={result.returncode}): {result.stderr[-500:]}")
    else:
        print("[Setup] Dependencies ready.")


def _set_env(config: dict):
    """Inject config values as env vars so the kernel script reads them."""
    env_map = {
        "APEX_BASE_MODEL":    config.get("base_model",            "unsloth/llama-3.1-8b-bnb-4bit"),
        "APEX_MAX_SEQ_LEN":   str(config.get("max_seq_length",    2048)),
        "APEX_LORA_RANK":     str(config.get("lora_rank",         16)),
        "APEX_LORA_ALPHA":    str(config.get("lora_alpha",        16)),
        "APEX_NUM_EPOCHS":    str(config.get("num_epochs",        3)),
        "APEX_BATCH_SIZE":    str(config.get("batch_size",        2)),
        "APEX_GRAD_ACCUM":    str(config.get("gradient_accumulation", 4)),
        "APEX_LEARNING_RATE": str(config.get("learning_rate",     2e-4)),
        "APEX_QUANT_TYPE":    config.get("quant_type",            "q4_k_m"),
        "APEX_TRAIN_FILE":    TRAIN_FILE,
        "APEX_OUTPUT_DIR":    OUTPUT_DIR,
        "APEX_MERGED_DIR":    MERGED_DIR,
        "APEX_GGUF_OUTPUT":   GGUF_OUTPUT,
    }
    os.environ.update(env_map)
    return env_map


def _upload(file_path: str, filename: str) -> str | None:
    """Upload a file via RunPod's managed S3 and return the presigned URL."""
    if not Path(file_path).exists():
        print(f"[Upload] File not found: {file_path}")
        return None
    size_gb = Path(file_path).stat().st_size / 1e9
    print(f"[Upload] Uploading {filename} ({size_gb:.2f} GB)...")
    try:
        import runpod.serverless.utils as rp_utils
        url = rp_utils.rp_upload(filename, file_path)
        print(f"[Upload] Done → {url[:80]}...")
        return url
    except Exception as e:
        print(f"[Upload] rp_upload failed ({e}). Trying file.io fallback...")
        # Fallback: file.io (free, expires 14 days, 5GB max)
        try:
            import urllib.request, urllib.parse
            with open(file_path, "rb") as f:
                boundary = "apexboundary"
                body = (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                    f"Content-Type: application/octet-stream\r\n\r\n"
                ).encode() + f.read() + f"\r\n--{boundary}--\r\n".encode()
            req = urllib.request.Request(
                "https://file.io/?expires=14d",
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST",
            )
            resp = json.loads(urllib.request.urlopen(req, timeout=3600).read())
            if resp.get("success"):
                url = resp["link"]
                print(f"[Upload] file.io fallback: {url}")
                return url
        except Exception as e2:
            print(f"[Upload] file.io fallback also failed: {e2}")
        return None


def handler(job: dict) -> dict:
    """RunPod serverless job handler — called once per job."""
    t0 = time.time()
    inp = job.get("input", {})
    config = inp.get("config", {})

    print(f"\n{'='*60}")
    print("APEX RunPod Fine-Tuning Handler")
    print(f"  Job ID  : {job.get('id', 'unknown')}")
    print(f"  Config  : {json.dumps({k: v for k, v in config.items() if 'key' not in k.lower()}, indent=2)}")
    print(f"{'='*60}\n")

    # ── Setup ──────────────────────────────────────────────────────────────────
    Path(WORK_DIR).mkdir(parents=True, exist_ok=True)
    _install_deps()

    # Write training JSONL
    data_b64 = inp.get("training_data_b64", "")
    if not data_b64:
        return {"status": "error", "error": "No training_data_b64 in input"}
    try:
        training_bytes = base64.b64decode(data_b64)
        Path(TRAIN_FILE).write_bytes(training_bytes)
        line_count = training_bytes.count(b"\n")
        print(f"[Setup] Training data: {len(training_bytes):,} bytes, ~{line_count} examples")
    except Exception as e:
        return {"status": "error", "error": f"Failed to decode training data: {e}"}

    # Set env vars for the kernel script
    _set_env(config)

    # ── Run fine-tuning kernel ─────────────────────────────────────────────────
    print(f"\n[Train] Running fine-tuning kernel: {KERNEL_SCRIPT}")
    if not Path(KERNEL_SCRIPT).exists():
        return {"status": "error", "error": f"Kernel script not found: {KERNEL_SCRIPT}"}

    rc = subprocess.run([sys.executable, KERNEL_SCRIPT]).returncode
    train_runtime = int(time.time() - t0)
    if rc != 0:
        print(f"[Train] Kernel exited with rc={rc}")
        # Don't fail — partial outputs (LoRA adapters) may still be available

    # ── Collect results ────────────────────────────────────────────────────────
    gguf_exists    = Path(GGUF_OUTPUT).exists()
    adapter_exists = (Path(OUTPUT_DIR) / "adapter_model.safetensors").exists()
    gguf_size_gb   = Path(GGUF_OUTPUT).stat().st_size / 1e9 if gguf_exists else 0

    print(f"\n[Results]")
    print(f"  GGUF    : {'YES (' + str(round(gguf_size_gb, 1)) + ' GB)' if gguf_exists else 'NO'}")
    print(f"  Adapters: {'YES' if adapter_exists else 'NO'}")
    print(f"  Runtime : {train_runtime // 60}m {train_runtime % 60}s")

    # ── Upload outputs ─────────────────────────────────────────────────────────
    gguf_url    = _upload(GGUF_OUTPUT,                                    "apex_trading_model.gguf") if gguf_exists else None
    adapter_url = _upload(str(Path(OUTPUT_DIR) / "adapter_model.safetensors"), "adapter_model.safetensors") if adapter_exists else None

    if not gguf_url and not adapter_url:
        return {
            "status": "error",
            "error":  f"Training completed (rc={rc}) but no output files found and upload failed",
            "train_runtime_s": train_runtime,
        }

    # Read final train loss from trainer_state.json if available
    train_loss = None
    for state_path in [
        Path(OUTPUT_DIR) / "trainer_state.json",
        Path(WORK_DIR)   / "checkpoints" / "trainer_state.json",
    ]:
        if state_path.exists():
            try:
                ts = json.loads(state_path.read_text())
                logs = ts.get("log_history", [])
                if logs:
                    train_loss = logs[-1].get("loss") or logs[-1].get("train_loss")
            except Exception:
                pass
            break

    return {
        "status":          "done",
        "gguf_url":        gguf_url,
        "adapter_url":     adapter_url,
        "gguf_size_gb":    round(gguf_size_gb, 2),
        "train_loss":      train_loss,
        "train_runtime_s": train_runtime,
        "kernel_rc":       rc,
    }


# ── Entry point ────────────────────────────────────────────────────────────────
runpod.serverless.start({"handler": handler})

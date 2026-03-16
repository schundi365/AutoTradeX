"""
APEX Bot — Remote Training Orchestration (Kaggle)
Automates the full Kaggle GPU fine-tuning pipeline:
  1. Upload training JSONL as a Kaggle dataset
  2. Push a kernel (GPU script) with embedded hyperparams
  3. Poll kernel status until complete (up to 4h)
  4. Download model output → local models/ directory

Prerequisites:
    pip install kaggle   (tested with kaggle 2.0.0)

Usage:
    python scripts/run_remote_training.py
    python scripts/run_remote_training.py --username myuser --key abc123
    python scripts/run_remote_training.py --gpu gpu_t4_x2  # Kaggle Pro dual-T4

Credentials are read from env vars KAGGLE_USERNAME / KAGGLE_KEY,
or from settings.training.kaggle_username / kaggle_api_key (dashboard config).
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import settings as _settings


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_api(username: str, api_key: str):
    """Return an authenticated KaggleApi instance (kaggle 2.0+).

    Writes ~/.kaggle/kaggle.json AND sets env vars before importing.
    The credentials file is required for blob upload (dataset create/update)
    even when env vars are set — kaggle 2.0's gRPC upload endpoint reads it.
    Raises RuntimeError (not SystemExit) so the background task handler
    can catch it and update job status.
    """
    import json as _json

    # Write ~/.kaggle/kaggle.json — required for blob upload in kaggle 2.0
    kaggle_dir = Path.home() / ".kaggle"
    kaggle_dir.mkdir(parents=True, exist_ok=True)
    kaggle_json = kaggle_dir / "kaggle.json"
    kaggle_json.write_text(
        _json.dumps({"username": username, "key": api_key}), encoding="utf-8"
    )
    try:
        kaggle_json.chmod(0o600)
    except Exception:
        pass  # chmod not critical on Windows

    # Also set env vars — kaggle 2.0 checks these on module init
    os.environ["KAGGLE_USERNAME"] = username
    os.environ["KAGGLE_KEY"] = api_key

    try:
        from kaggle import KaggleApi          # kaggle 2.0.0
    except ImportError:
        raise RuntimeError(
            "kaggle package not installed. Run: pip install kaggle"
        )

    api = KaggleApi()
    api.authenticate()
    print(f"  [Kaggle] Authenticated as '{username}'")
    return api


def _slug(name: str) -> str:
    """Convert a name to a Kaggle-safe slug (lowercase, hyphens only)."""
    import re
    return re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Upload training data as a Kaggle dataset
# ─────────────────────────────────────────────────────────────────────────────

def upload_training_data(
    api,
    username: str,
    dataset_slug: str,
    training_jsonl: Path,
) -> str:
    """Upload the training JSONL to Kaggle as a private dataset.

    Returns the full dataset ref: '{username}/{dataset_slug}'.
    """
    dataset_ref = f"{username}/{dataset_slug}"
    file_size_kb = training_jsonl.stat().st_size // 1024
    print(f"  [Kaggle] Uploading training data → '{dataset_ref}' ({file_size_kb} KB)...")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Copy training file into temp folder
        shutil.copy2(training_jsonl, tmp_path / "apex_training_latest.jsonl")

        # Dataset metadata (kaggle 2.0 uses dataset-metadata.json)
        meta = {
            "title": "APEX Training Data",
            "id": dataset_ref,
            "licenses": [{"name": "other"}],
        }
        (tmp_path / "dataset-metadata.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )

        # Try create_new first. If dataset already exists, update version.
        try:
            api.dataset_create_new(
                folder=tmp,
                public=False,
                quiet=False,
                convert_to_csv=False,
                dir_mode="skip",
            )
            print(f"    Created new dataset '{dataset_ref}'")
        except Exception as create_err:
            err_str = str(create_err).lower()
            print(f"    dataset_create_new: {create_err}")
            if any(k in err_str for k in ("already", "exist", "conflict", "409", "duplicate")):
                print(f"    Dataset exists — uploading new version...")
                api.dataset_create_version(
                    folder=tmp,
                    version_notes=f"apex-bot {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
                    quiet=False,
                    convert_to_csv=False,
                    delete_old_versions=False,
                    dir_mode="skip",
                )
                print(f"    Updated dataset '{dataset_ref}' with new version")
            else:
                raise RuntimeError(f"Dataset upload failed: {create_err}") from create_err

    return dataset_ref


# ─────────────────────────────────────────────────────────────────────────────
# 2. Push the fine-tuning kernel
# ─────────────────────────────────────────────────────────────────────────────

def push_kernel(
    api,
    username: str,
    kernel_slug: str,
    dataset_ref: str,
    config: dict,
) -> str:
    """Upload and push the fine-tuning kernel to Kaggle.

    Returns the ACTUAL kernel ref as reported by Kaggle in the push response
    (resp.ref). Kaggle derives the slug from the title, not the metadata id,
    so we always use resp.ref for subsequent status/download calls.

    The kernel code (kaggle_finetune_kernel.py) is INLINED into the runner
    script so no file-path tricks are needed on the Kaggle executor.
    """
    kernel_ref = f"{username}/{kernel_slug}"
    print(f"  [Kaggle] Pushing kernel '{kernel_ref}'...")

    kernel_script_src = Path(__file__).parent / "kaggle_finetune_kernel.py"
    if not kernel_script_src.exists():
        raise RuntimeError(f"Kernel script not found: {kernel_script_src}")

    # Read kernel code to inline — avoids any Kaggle file-path issues.
    # Strip 'from __future__' imports: they must appear at the top of a file,
    # but our runner already starts with 'import os', so inlining them later
    # would cause a SyntaxError.
    import re as _re, base64 as _b64, gzip as _gz
    kernel_code = kernel_script_src.read_text(encoding="utf-8")
    kernel_code = _re.sub(r"^from __future__ import[^\n]*\n?", "", kernel_code, flags=_re.MULTILINE)

    # Embed training JSONL as base64 directly in the runner script.
    # This is more reliable than Kaggle dataset mounting, which can silently
    # fail when a newly-uploaded private dataset version hasn't propagated.
    training_jsonl_path = Path(config.get("training_data_dir", "training_data")) / "apex_training_latest.jsonl"
    if not training_jsonl_path.exists():
        raise RuntimeError(f"Training JSONL not found: {training_jsonl_path}")
    
    # Compress data to stay under Kaggle's 1MB script limit.
    # 1MB JSONL -> ~100KB gzip -> ~133KB b64.
    training_gz = _gz.compress(training_jsonl_path.read_bytes())
    training_b64 = _b64.b64encode(training_gz).decode("ascii")
    
    embed_lines = (
        "# ── Embedded training data (base64 + gzip) ──────────────────────────────────\n"
        "import base64 as _b64, pathlib as _pl, gzip as _gz\n"
        "_train_path = _pl.Path('/kaggle/working/apex_training_latest.jsonl')\n"
        f"_gz_data = _b64.b64decode('{training_b64}')\n"
        "_train_path.write_bytes(_gz.decompress(_gz_data))\n"
        f"print(f'Embedded training data: {{_train_path}} ({{_train_path.stat().st_size}} bytes)')\n"
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Cap max_seq_len at 512 for Kaggle T4 (16GB VRAM) to prevent OOM.
        # GO/NOGO prompts are short — 512 tokens is more than enough.
        _seq_len = min(int(config.get("max_seq_length", 512)), 512)
        env_lines = "\n".join([
            f'os.environ["APEX_BASE_MODEL"]    = {json.dumps(str(config.get("base_model", "unsloth/llama-3.1-8b-bnb-4bit")))}',
            f'os.environ["APEX_MAX_SEQ_LEN"]   = {json.dumps(str(_seq_len))}',
            f'os.environ["APEX_LORA_RANK"]     = {json.dumps(str(config.get("lora_rank", 8)))}',
            f'os.environ["APEX_LORA_ALPHA"]    = {json.dumps(str(config.get("lora_alpha", 16)))}',
            f'os.environ["APEX_NUM_EPOCHS"]    = {json.dumps(str(config.get("num_epochs", 1)))}',
            f'os.environ["APEX_BATCH_SIZE"]    = {json.dumps(str(config.get("batch_size", 1)))}',
            f'os.environ["APEX_GRAD_ACCUM"]    = {json.dumps(str(config.get("gradient_accumulation", 8)))}',
            f'os.environ["APEX_LEARNING_RATE"] = {json.dumps(str(config.get("learning_rate", 2e-4)))}',
            f'os.environ["APEX_QUANT_TYPE"]    = {json.dumps(str(config.get("quant_type", "q4_k_m")))}',
            # Skip fp16 merge on Kaggle T4 — loading 8B fp16 (~16GB) + merge overhead OOMs 30GB RAM.
            # LoRA adapters are downloaded and merged locally by the Convert step instead.
            'os.environ["APEX_SKIP_MERGE"]    = "1"',
            # TRAIN_FILE points to /kaggle/working/ where we write the embedded data
            'os.environ["APEX_TRAIN_FILE"]    = "/kaggle/working/apex_training_latest.jsonl"',
        ])

        # Single self-contained script: env vars + embedded data + inlined kernel
        runner_code = (
            "# APEX Kaggle Runner — auto-generated by run_remote_training.py\n"
            "import os\n"
            f"{env_lines}\n\n"
            f"{embed_lines}\n"
            "# ── Inlined from scripts/kaggle_finetune_kernel.py ──────────────────────────\n"
            f"{kernel_code}\n"
        )
        (tmp_path / "kaggle_runner.py").write_text(runner_code, encoding="utf-8")

        # Use a dynamic title derived from the slug to satisfy Kaggle's resolver.
        # title: apex-qlora-finetune -> APEX QLoRA Finetune
        kernel_title = kernel_slug.replace("-", " ").title()
        # Edge case: Kaggle's logic for slugification sometimes differs.
        # We ensure it's simple.
        meta = {
            "id": kernel_ref,
            "title": kernel_title,
            "code_file": "kaggle_runner.py",
            "language": "python",
            "kernel_type": "script",
            "is_private": True,
            "enable_gpu": True,
            "enable_internet": True,
            "dataset_sources": [],
            "competition_sources": [],
            "kernel_sources": [],
        }
        print(f"    [DEBUG] Metadata: {json.dumps(meta)}")
        (tmp_path / "kernel-metadata.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )

        # gpu_type → kaggle 2.0 acc parameter
        # "gpu" = T4 free, "gpu_t4_x2" = Pro dual-T4, "nvidiagpup100" = P100 free
        gpu_type = config.get("gpu_type", "gpu")
        acc = gpu_type if gpu_type in ("gpu", "gpu_t4_x2", "nvidiagpup100") else "gpu"

        print(f"    Runner: {len(runner_code):,} chars | Accelerator: {acc}")
        try:
            # kaggle-api 2.0+ handles accelerator mapping.
            # Try with provided accelerator parameter first.
            resp = api.kernels_push(tmp)
            print(f"    Push response type: {type(resp)}")
            # For Kaggle 2.0, try to print its attributes
            try:
                print(f"    Push response attributes: {dir(resp)}")
                print(f"    Push response ref: {getattr(resp, 'ref', 'N/A')}")
                print(f"    Push response url: {getattr(resp, 'url', 'N/A')}")
            except:
                pass
            print(f"    Push response raw: {resp}")
        except Exception as e:
            err_msg = str(e).lower()
            if "400" in err_msg or "bad request" in err_msg:
                print("\n    [KAGGLE] ERROR 400: This usually happens if:")
                print("      1. The kernel SLUG (id) already exists but is a 'Notebook' (this push is a 'Script').")
                print("      2. You reached your weekly GPU limit.")
                print("      3. The accelerator type or metadata is invalid.")
                print(f"    Details: {e}")
                
                # Help the user resolve it by suggesting the specific change
                new_suggestion = f"{kernel_slug}-script"
                print(f"\n    [TIP] Try changing 'Kaggle Kernel Name' to '{new_suggestion}' in Training Config.")
                
                raise RuntimeError(
                    f"Kaggle push failed (400 Bad Request). If this kernel ID '{kernel_ref}' was "
                    "manually created as a Notebook, you MUST delete it on Kaggle or change the "
                    f"kernel_name to something like '{new_suggestion}' in your dashboard config."
                ) from e
            elif "409" in err_msg or "conflict" in err_msg:
                print("\n    [KAGGLE] ERROR 409: This usually happens if:")
                print(f"      1. A kernel with name '{kernel_slug}' is already running/saving.")
                print("      2. There is a deep metadata conflict (e.g. title logic changed).")
                print("    [TIP] Wait 1 minute or use a completely new 'Kaggle Kernel Name' in config.")
                raise RuntimeError(
                    f"Kaggle push conflict (409). A kernel with name '{kernel_slug}' may be in "
                    "an active state. Try a unique name like 'apex-finetune-v2' if this persists."
                ) from e
            raise RuntimeError(f"kernels_push failed: {e}") from e

        # resp.ref is in the form "/code/{username}/{slug}" — strip the
        # "/code/" prefix so kernels_status gets a bare "username/slug" ref.
        actual_ref = (getattr(resp, "ref", None) or "").strip()
        if actual_ref.startswith("/code/"):
            actual_ref = actual_ref[len("/code/"):]
        actual_ref = actual_ref or kernel_ref   # fallback to local slug
        if actual_ref != kernel_ref:
            print(f"    Kaggle assigned ref: '{actual_ref}' (requested '{kernel_ref}')")
        
        # Explicit error check in the response (Kaggle 2.0 might not raise on all errors)
        resp_error = getattr(resp, "error", None) or (resp.get("error") if hasattr(resp, "get") else None)
        if resp_error:
            print(f"\n    [KAGGLE] API returned error in response: {resp_error}")
            raise RuntimeError(f"Kaggle push failed: {resp_error}")
            
        print(f"    Kernel live: https://www.kaggle.com/code/{actual_ref}")

    return actual_ref


# ─────────────────────────────────────────────────────────────────────────────
# 3. Poll until kernel finishes
# ─────────────────────────────────────────────────────────────────────────────

def poll_kernel(
    api,
    kernel_ref: str,
    poll_interval: int = 30,
    timeout_hours: float = 4.0,
) -> dict:
    """Poll Kaggle kernel status until complete or timeout.

    kernel_ref is the ACTUAL ref returned by push_kernel (e.g. 'user/slug').
    kaggle 2.0: kernels_status(kernel) takes a single "owner/slug" string.

    Returns dict with keys: status ('complete'|'error'), url, total_seconds.
    """
    max_seconds = int(timeout_hours * 3600)
    elapsed = 0
    last_status = None
    consecutive_errors = 0

    print(f"\n  [Kaggle] Polling kernel (every {poll_interval}s, timeout {timeout_hours}h)...")
    print(f"    Live: https://www.kaggle.com/code/{kernel_ref}")
    
    # Wait for propagation (404s are common immediately after push)
    time.sleep(10)

    while elapsed < max_seconds:
        try:
            # kaggle 2.0: single-arg call with "username/slug"
            print(f"    [{datetime.utcnow().strftime('%H:%M:%S')}] Polling status for '{kernel_ref}'...")
            status_obj = api.kernels_status(kernel_ref)

            # Extract status string from response object
            status = getattr(status_obj, "status", None)
            if status is None and hasattr(status_obj, "get"):
                status = status_obj.get("status")
            status = str(status).lower() if status else "unknown"
            # Kaggle 2.0 returns "kernelworkerstatus.complete" etc.
            # Normalise to the final word: "kernelworkerstatus.complete" → "complete"
            status_key = status.rsplit(".", 1)[-1]

            # Extract failure message if available
            failure = (
                getattr(status_obj, "failure_message", None)
                or getattr(status_obj, "failureMessage", None)
                or (status_obj.get("failureMessage") if hasattr(status_obj, "get") else None)
            )

            if status != last_status:
                ts = datetime.utcnow().strftime("%H:%M:%S")
                msg = f"    [{ts}] status: {status}"
                if failure:
                    msg += f" — {failure}"
                print(msg)
                last_status = status

            consecutive_errors = 0

            if status_key in ("complete", "complete_with_errors"):
                return {
                    "status": "complete",
                    "url": f"https://www.kaggle.com/code/{kernel_ref}",
                    "total_seconds": elapsed,
                }
            if status_key in ("error", "cancelled", "cancel_requested"):
                return {
                    "status": "error",
                    "url": f"https://www.kaggle.com/code/{kernel_ref}",
                    "total_seconds": elapsed,
                    "error": f"Kernel ended '{status}'" + (f": {failure}" if failure else ""),
                }

        except Exception as e:
            err_str = str(e).lower()
            # 404 is often transient shortly after push
            if "404" in err_str:
                if elapsed < 300: # 5 mins
                    print(f"    [Kaggle] Kernel not found yet (404)... waiting to propagate.")
                    consecutive_errors = 0 # Don't count 404s as hard failures early on
                else:
                    # After 5 mins of 404, let's list kernels to see if it's there under a diff name
                    try:
                        print(f"    [DEBUG] Polling failed with 404 for 5+ min. Listing your kernels...")
                        kernels = api.kernels_list(user=kernel_ref.split('/')[0])
                        print(f"    [DEBUG] Found {len(kernels)} kernels on your account:")
                        for k in kernels[:5]:
                            print(f"      - {getattr(k, 'ref', 'N/A')} (status: {getattr(k, 'status', 'N/A')})")
                    except Exception as list_err:
                        print(f"    [DEBUG] Failed to list kernels: {list_err}")
                    consecutive_errors += 1
            else:
                consecutive_errors += 1
            
            print(f"    WARNING: poll error #{consecutive_errors}: {e}")
            if consecutive_errors >= 10: # Increased from 5 to 10
                return {
                    "status": "error",
                    "url": f"https://www.kaggle.com/code/{kernel_ref}",
                    "total_seconds": elapsed,
                    "error": f"Polling failed {consecutive_errors}x: {e}",
                }

        time.sleep(poll_interval)
        elapsed += poll_interval

    return {
        "status": "error",
        "url": f"https://www.kaggle.com/code/{kernel_ref}",
        "total_seconds": elapsed,
        "error": f"Timeout after {timeout_hours}h — check at kaggle.com",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Download kernel output
# ─────────────────────────────────────────────────────────────────────────────

def download_output(
    api,
    kernel_ref: str,
    output_dir: str,
) -> list[str]:
    """Download all kernel output files to output_dir.

    Uses the kaggle CLI via subprocess (Method 1) instead of calling the
    Python API directly. The Python API's internal print()/tqdm calls raise
    UnicodeEncodeError on Windows cp1252 even with quiet=True because the
    Kaggle package writes to sys.__stdout__ (the original stream reference)
    rather than the currently-assigned sys.stdout. A subprocess has its own
    isolated streams and avoids this entirely.

    Falls back to the Python API (Method 2) with all standard streams silenced
    if the subprocess approach fails.
    """
    import subprocess as _sp
    import sys as _sys

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Snapshot existing files so we can report what was newly downloaded
    _before = {str(f) for f in out_path.rglob("*") if f.is_file()}

    print(f"\n  [Kaggle] Downloading kernel output → {out_path}...")

    # ── Method 1: subprocess kaggle CLI ──────────────────────────────────────
    # Child process has its own stdout/stderr — no encoding bleed-through.
    # We pass PYTHONIOENCODING=utf-8 so the CLI itself uses UTF-8 too.
    # Use the kaggle entry-point exe from the same venv (not python -m kaggle,
    # which fails because kaggle has no __main__.py).
    _scripts_dir = Path(_sys.executable).parent
    _kaggle_exe = _scripts_dir / ("kaggle.exe" if _sys.platform == "win32" else "kaggle")
    if not _kaggle_exe.exists():
        _kaggle_exe = Path("kaggle")   # fallback: hope it's on PATH
    try:
        cmd = [
            str(_kaggle_exe),
            "kernels", "output", kernel_ref,
            "--path", str(out_path),
            "--force",   # overwrite existing local copies
        ]
        _cli_env = {
            **os.environ,
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",          # Python 3.7+ — forces UTF-8 everywhere in the subprocess
        }
        proc = _sp.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_cli_env,
        )
        if proc.stdout.strip():
            for line in proc.stdout.strip().splitlines():
                print(f"    kaggle: {line}")
        if proc.returncode == 0:
            newly = [str(f) for f in out_path.rglob("*") if f.is_file()
                     and str(f) not in _before]
            print(f"    CLI download OK — {len(newly)} new file(s)")
            return newly or [str(f) for f in out_path.rglob("*") if f.is_file()]
        else:
            stderr_snippet = (proc.stderr or "").strip()[:400]
            print(f"    CLI rc={proc.returncode}: {stderr_snippet}")
            # fall through to Method 2
    except Exception as e:
        print(f"    CLI method unavailable ({e}), trying API...")

    # ── Method 2: Python API with fully silenced streams ─────────────────────
    # Replace sys.stdout, sys.stderr, sys.__stdout__, sys.__stderr__ with a
    # no-op sink so any internal print() in the Kaggle API is discarded safely.
    class _NullSink:
        def write(self, s): pass
        def flush(self): pass
        def __getattr__(self, n): return lambda *a, **k: None

    _sink = _NullSink()
    _saved_out  = _sys.stdout
    _saved_err  = _sys.stderr
    _saved_out2 = getattr(_sys, "__stdout__", None)
    _saved_err2 = getattr(_sys, "__stderr__", None)
    try:
        _sys.stdout = _sys.stderr = _sink
        try:
            _sys.__stdout__ = _sink   # type: ignore[attr-defined]
            _sys.__stderr__ = _sink   # type: ignore[attr-defined]
        except Exception:
            pass

        result = api.kernels_output(kernel_ref, path=str(out_path), quiet=True, force=True)

        newly = [str(f) for f in out_path.rglob("*") if f.is_file()
                 and str(f) not in _before]
        if isinstance(result, tuple) and isinstance(result[0], list):
            newly = newly or result[0]
        _saved_out.write(f"    API fallback — {len(newly)} new file(s)\n")
        return newly
    except Exception as e:
        _saved_out.write(f"    API fallback also failed: {e}\n")
        return []
    finally:
        _sys.stdout = _saved_out
        _sys.stderr = _saved_err
        if _saved_out2 is not None:
            try:
                _sys.__stdout__ = _saved_out2   # type: ignore[attr-defined]
                _sys.__stderr__ = _saved_err2   # type: ignore[attr-defined]
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# 5. Full pipeline
# ─────────────────────────────────────────────────────────────────────────────

def run_on_kaggle(config: dict) -> dict:
    """Run the complete Kaggle remote training pipeline."""
    t0 = time.time()

    username     = config.get("username", "")
    api_key      = config.get("api_key", "")
    dataset_slug = _slug(config.get("dataset_name", "apex-training-data"))
    kernel_slug  = _slug(config.get("kernel_name",  "apex-qlora-finetune"))
    training_dir = config.get("training_data_dir", "training_data")
    output_dir   = config.get("model_output_dir",  "models/apex_training_model")

    if not username:
        return {"status": "error", "error": "Kaggle username not configured — set in Training Config"}
    if not api_key:
        return {"status": "error", "error": "Kaggle API key not configured — set in Training Config"}

    training_jsonl = Path(training_dir) / "apex_training_latest.jsonl"
    if not training_jsonl.exists():
        return {
            "status": "error",
            "error": f"Training data not found: {training_jsonl}. Run Export (Step 3) first.",
        }

    print(f"\n{'='*60}")
    print("APEX Remote Training — Kaggle GPU")
    print(f"  User     : {username}")
    print(f"  Dataset  : {dataset_slug}")
    print(f"  Kernel   : {kernel_slug}")
    print(f"  GPU      : {config.get('gpu_type', 'gpu')}")
    print(f"  Data     : {training_jsonl} ({training_jsonl.stat().st_size // 1024} KB)")
    print(f"{'='*60}\n")

    # Authenticate
    try:
        api = _get_api(username, api_key)
    except Exception as e:
        return {"status": "error", "error": f"Kaggle auth failed: {e}"}

    # Step 1 — upload training data
    try:
        dataset_ref = upload_training_data(api, username, dataset_slug, training_jsonl)
    except Exception as e:
        return {"status": "error", "error": f"Dataset upload failed: {e}"}

    print("  Waiting 60s for dataset to propagate on Kaggle...")
    time.sleep(60)

    # Step 2 — push kernel; capture actual ref assigned by Kaggle
    try:
        actual_kernel_ref = push_kernel(api, username, kernel_slug, dataset_ref, config)
    except Exception as e:
        return {"status": "error", "error": f"Kernel push failed: {e}"}

    # Step 3 — poll until done (use actual ref, not locally computed slug)
    try:
        poll_result = poll_kernel(api, actual_kernel_ref)
    except Exception as e:
        return {"status": "error", "error": f"Polling failed: {e}"}

    if poll_result["status"] != "complete":
        return {
            "status": "error",
            "error": poll_result.get("error", "Kernel did not complete"),
            "url": poll_result.get("url"),
            "duration_seconds": int(time.time() - t0),
        }

    # Step 4 — download model output (use actual ref)
    try:
        downloaded = download_output(api, actual_kernel_ref, output_dir)
    except Exception as e:
        print(f"  WARNING: Output download failed: {e}")
        downloaded = []

    duration = int(time.time() - t0)

    # Detect if a GGUF was downloaded (Kaggle kernel now converts on GPU)
    gguf_files = list(Path(output_dir).rglob("*.gguf"))
    gguf_path = str(gguf_files[0]) if gguf_files else None
    if gguf_path:
        gguf_size_gb = Path(gguf_path).stat().st_size / 1e9
        print(f"  GGUF downloaded: {gguf_path} ({gguf_size_gb:.1f} GB) — skip local merge/convert!")
    else:
        print("  No GGUF found — local Convert step will merge adapters and convert.")

    print(f"\n{'='*60}")
    print(f"Kaggle training complete in {duration // 60}m {duration % 60}s")
    print(f"  Model: {output_dir} | Files: {len(downloaded)}")
    print(f"  URL  : {poll_result['url']}")
    print(f"{'='*60}")
    if gguf_path:
        print("Next: Load GGUF into Ollama (Step 5 will use the downloaded GGUF)")
    else:
        print("Next: Run Convert → GGUF (Step 5) — will merge adapters locally")

    return {
        "status": "done",
        "model_dir": output_dir,
        "duration_seconds": duration,
        "url": poll_result["url"],
        "files_downloaded": len(downloaded),
        "gguf_path": gguf_path,   # set if Kaggle did the conversion
    }


# ─────────────────────────────────────────────────────────────────────────────

def main():
    tr = _settings.training
    parser = argparse.ArgumentParser(description="APEX Kaggle remote training")
    parser.add_argument("--username", default=None)
    parser.add_argument("--key",      default=None)
    parser.add_argument("--dataset",  default=None, help=f"default: {tr.kaggle_dataset_name}")
    parser.add_argument("--kernel",   default=None, help=f"default: {tr.kaggle_kernel_name}")
    parser.add_argument("--gpu",      default=None, help=f"gpu | gpu_t4_x2 | nvidiagpup100 (default: {tr.kaggle_gpu_type})")
    parser.add_argument("--data",     default=None, help=f"default: {tr.training_data_dir}")
    parser.add_argument("--out",      default=None, help=f"default: {tr.model_output_dir}")
    args = parser.parse_args()

    result = run_on_kaggle({
        "username":              args.username or tr.kaggle_username,
        "api_key":               args.key      or tr.kaggle_api_key,
        "dataset_name":          args.dataset  or tr.kaggle_dataset_name,
        "kernel_name":           args.kernel   or tr.kaggle_kernel_name,
        "gpu_type":              args.gpu      or tr.kaggle_gpu_type,
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
    })

    if result["status"] == "error":
        print(f"\nERROR: {result['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()

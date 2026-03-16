"""
APEX Trading Bot — LoRA → GGUF → Ollama Pipeline
=================================================
Merges downloaded LoRA adapters into the fp16 base model locally,
converts to GGUF, and registers as `apex-trader` in Ollama.

Steps
-----
  1. Install CPU torch + transformers + peft + gguf (pip, one-time)
  2. Patch adapter_config.json (bnb-4bit base → fp16 equivalent)
  3. Merge LoRA into base model on CPU  (~16 GB RAM, 10-30 min)
  4. Download llama.cpp convert_hf_to_gguf.py (once, ~50 KB)
  5. Convert merged safetensors → GGUF F16  (~16 GB output)
  5b. Quantize F16 GGUF → Q4_K_M (~4.5 GB) via llama-quantize if available
  6. Write Ollama Modelfile with APEX system prompt
  7. ollama create apex-trader -f Modelfile

Usage
-----
  python scripts/deploy_ollama.py                       # defaults
  python scripts/deploy_ollama.py --skip-merge          # if merge already done
  python scripts/deploy_ollama.py --adapter lora_output --name apex-trader
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

# Block TF/JAX backends BEFORE any transformers import.
# Without this, transformers tries to import TensorFlow as optional backend,
# which then crashes on a protobuf version mismatch with the system TF install.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_JAX", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

ROOT = Path(__file__).resolve().parent.parent

# ── 4-bit quantized → fp16 base model map ────────────────────────────────────
_BNB_TO_FP16: dict[str, str] = {
    "unsloth/llama-3.1-8b-bnb-4bit":                    "unsloth/Meta-Llama-3.1-8B",
    "unsloth/Llama-3.1-8B-bnb-4bit":                    "unsloth/Meta-Llama-3.1-8B",
    "unsloth/llama-3.1-8b-instruct-bnb-4bit":            "unsloth/Meta-Llama-3.1-8B-Instruct",
    "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit":       "unsloth/Meta-Llama-3.1-8B-Instruct",
    "unsloth/llama-3-8b-bnb-4bit":                       "unsloth/Meta-Llama-3-8B",
    "unsloth/mistral-7b-v0.3-bnb-4bit":                  "unsloth/mistral-7b-v0.3",
}

# llama.cpp convert script — downloaded from master (needs pip install gguf)
_CONVERT_URL = (
    "https://raw.githubusercontent.com/ggerganov/llama.cpp/master/convert_hf_to_gguf.py"
)
_CONVERT_SCRIPT = ROOT / "scripts" / "_convert_hf_to_gguf.py"

# APEX trading system prompt injected into the Ollama model
_SYSTEM_PROMPT = """\
You are APEX, an expert algorithmic trading analyst specialising in Gold (XAUUSD), \
Forex, and Commodities.

When given a trading setup always respond in this exact format:

DECISION: APPROVE | REJECT
CONFIDENCE: 0.00-1.00

REASONING:
1. TREND: <EMA structure / price action>
2. MOMENTUM: <RSI reading and implication>
3. TREND STRENGTH: <ADX value and regime>
4. MACRO: <DXY / US10Y / macro context>
5. RISK: <ATR volatility and lot sizing>

ENTRY: Market | STOP: -1.5×ATR | TARGET: +2.5×ATR | ATR%: X.XX%
RISK_REWARD: 2.5:1

Be concise, data-driven, and never add commentary outside this format.\
"""


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, **kw)


def _pip(*packages: str):
    _run([sys.executable, "-m", "pip", "install", "--quiet", *packages])


def _importable(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def _check_ram_gb() -> float:
    try:
        import psutil
        return psutil.virtual_memory().available / 1e9
    except ImportError:
        return 999.0   # can't check → assume OK


# ─────────────────────────────────────────────────────────────────────────────
#  Step 1 — Install deps
# ─────────────────────────────────────────────────────────────────────────────

def ensure_deps():
    print("[1/7] Checking Python dependencies...")

    if not _importable("torch"):
        print("  Installing PyTorch (CPU-only, ~250 MB)...")
        _pip("torch", "--index-url", "https://download.pytorch.org/whl/cpu")

    missing = [
        pkg for pkg, mod in [
            ("transformers",   "transformers"),
            ("peft",           "peft"),
            ("accelerate",     "accelerate"),
            ("safetensors",    "safetensors"),
            ("sentencepiece",  "sentencepiece"),
            # NOTE: protobuf intentionally omitted — TensorFlow pins its own
            # version and upgrading it causes ImportError in TF.
            ("gguf",           "gguf"),
        ] if not _importable(mod)
    ]
    if missing:
        print(f"  Installing: {' '.join(missing)}")
        _pip(*missing)

    print("  ✓ All dependencies ready")


# ─────────────────────────────────────────────────────────────────────────────
#  Step 2 — Patch adapter_config.json
# ─────────────────────────────────────────────────────────────────────────────

def patch_adapter_config(adapter_path: Path) -> str:
    """Replace 4-bit base with fp16 equivalent. Returns the fp16 model ID."""
    print("\n[2/7] Patching adapter_config.json...")
    cfg_path = adapter_path / "adapter_config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    base = cfg.get("base_model_name_or_path", "")
    fp16 = _BNB_TO_FP16.get(base)

    if fp16:
        print(f"  {base}")
        print(f"  → {fp16}")
        cfg["base_model_name_or_path"] = fp16
        cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        return fp16

    print(f"  Base already fp16: {base}")
    return base


# ─────────────────────────────────────────────────────────────────────────────
#  Step 3 — Merge LoRA into fp16 base (CPU)
# ─────────────────────────────────────────────────────────────────────────────

def merge_lora(adapter_path: Path, base_model: str, output_path: Path):
    print(f"\n[3/7] Merging LoRA adapters into base model (CPU)...")
    print(f"      Base   : {base_model}")
    print(f"      Output : {output_path}")

    avail = _check_ram_gb()
    if avail < 14:
        print(f"  WARNING: Only {avail:.0f} GB RAM available — need ~16 GB.")
        print("  Continuing anyway; may be slow or fail if paged.")

    # Ensure TF/JAX are blocked even if subprocess env was different
    os.environ["USE_TF"] = "0"
    os.environ["USE_JAX"] = "0"
    os.environ["TRANSFORMERS_NO_TF"] = "1"

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    print("  Downloading / loading base model in fp16 on CPU...")
    print("  (First run downloads ~16 GB from HuggingFace — please wait)")
    base = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=torch.float16,
        low_cpu_mem_usage=True,
        trust_remote_code=True,
        device_map=None,          # avoid accelerate multi-device bug
    )
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)

    print("  Loading LoRA adapter...")
    model = PeftModel.from_pretrained(base, str(adapter_path), device_map=None)

    print("  Merging and unloading (may take several minutes)...")
    merged = model.merge_and_unload()

    print(f"  Saving merged model to {output_path}...")
    output_path.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(str(output_path), safe_serialization=True)
    tokenizer.save_pretrained(str(output_path))
    print("  ✓ Merge complete")

    # free memory before conversion
    del merged, model, base
    import gc
    gc.collect()


# ─────────────────────────────────────────────────────────────────────────────
#  Step 4 — Download llama.cpp convert script
# ─────────────────────────────────────────────────────────────────────────────

def get_convert_script():
    if _CONVERT_SCRIPT.exists():
        print(f"\n[4/7] Convert script already present — {_CONVERT_SCRIPT.name}")
        return
    print(f"\n[4/7] Downloading llama.cpp convert_hf_to_gguf.py...")
    try:
        urllib.request.urlretrieve(_CONVERT_URL, _CONVERT_SCRIPT)
        print(f"  ✓ Saved to {_CONVERT_SCRIPT}")
    except Exception as e:
        print(f"  ERROR downloading convert script: {e}")
        print(f"  Manual fix: download convert_hf_to_gguf.py from")
        print(f"  https://github.com/ggerganov/llama.cpp and place it at {_CONVERT_SCRIPT}")
        sys.exit(1)


# convert_hf_to_gguf.py only supports: f32, f16, bf16, q8_0, tq1_0, tq2_0, auto
# Q4_K_M / Q5_K_M require a separate llama-quantize pass after conversion.
_QUANT_TO_OUTTYPE: dict[str, str] = {
    "q4_k_m": "f16",   # convert to F16, then quantize via llama-quantize
    "q5_k_m": "f16",   # convert to F16, then quantize via llama-quantize
    "q8_0":   "q8_0",  # directly supported by convert script
    "f16":    "f16",
}

# llama-quantize type strings (None = no separate quantize step needed)
_QUANT_TO_LLAMACPP: dict[str, str | None] = {
    "q4_k_m": "Q4_K_M",
    "q5_k_m": "Q5_K_M",
    "q8_0":   None,
    "f16":    None,
}


# ─────────────────────────────────────────────────────────────────────────────
#  Step 5 — Convert to GGUF
# ─────────────────────────────────────────────────────────────────────────────

def convert_to_gguf(merged_path: Path, gguf_path: Path, quant: str = "q4_k_m"):
    outtype = _QUANT_TO_OUTTYPE.get(quant, "f16")
    print(f"\n[5/7] Converting to GGUF (outtype={outtype.upper()}, final quant={quant.upper()})...")
    gguf_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, str(_CONVERT_SCRIPT),
        str(merged_path),
        "--outfile", str(gguf_path),
        "--outtype", outtype,
    ]
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        # Print last 3000 chars of stderr for diagnosis
        err = (result.stdout + result.stderr)[-3000:]
        print(f"  FAILED — last output:\n{err}")
        raise RuntimeError(f"GGUF conversion failed (rc={result.returncode})")

    size_gb = gguf_path.stat().st_size / 1e9
    print(f"  ✓ GGUF saved: {gguf_path}  ({size_gb:.1f} GB)")
    if _QUANT_TO_LLAMACPP.get(quant):
        print(f"  ℹ  Will attempt Q4/Q5 quantization via llama-quantize in next step")


# ─────────────────────────────────────────────────────────────────────────────
#  Step 5b — Quantize F16 GGUF → Q4_K_M via llama-quantize (optional)
# ─────────────────────────────────────────────────────────────────────────────

def _find_llama_quantize() -> str | None:
    """Return path to llama-quantize binary, or None if not found."""
    import shutil
    candidates = [
        "llama-quantize",
        "llama-quantize.exe",
        # Safe locations — do NOT place llama-quantize.exe in the Ollama install
        # folder; llama.cpp releases include ggml-base.dll which overwrites Ollama's
        # runtime library and causes inference to hang.
        r"C:\tools\llama-quantize.exe",
        r"C:\Users\srika\bin\llama-quantize.exe",
        str(ROOT / "llama.cpp" / "llama-quantize"),
        str(ROOT / "llama.cpp" / "llama-quantize.exe"),
        str(ROOT / "llama.cpp" / "build" / "bin" / "llama-quantize"),
        str(ROOT / "llama.cpp" / "build" / "bin" / "Release" / "llama-quantize.exe"),
    ]
    for c in candidates:
        if shutil.which(c) or Path(c).exists():
            return c
    return None


def quantize_gguf(f16_path: Path, quant: str) -> Path:
    """
    Quantize an F16 GGUF to Q4_K_M/Q5_K_M using llama-quantize.
    Returns the path to the quantized GGUF (or f16_path if skipped).
    """
    llama_quant_type = _QUANT_TO_LLAMACPP.get(quant)
    if not llama_quant_type:
        # q8_0 or f16 — no extra step needed
        return f16_path

    # Output path: same dir, different name  e.g. apex-trader-q4_k_m.gguf
    q_path = f16_path.with_name(f16_path.stem + f"-{quant}.gguf")

    binary = _find_llama_quantize()
    if binary is None:
        print(f"\n[5b/7] llama-quantize not found — skipping quantization.")
        print(f"       The F16 GGUF will be loaded into Ollama (~16 GB RAM needed).")
        print(f"       To quantize later: download llama-quantize from")
        print(f"       https://github.com/ggerganov/llama.cpp/releases")
        print(f"       then run: llama-quantize {f16_path} {q_path} {llama_quant_type}")
        return f16_path

    print(f"\n[5b/7] Quantizing F16 GGUF → {quant.upper()} via llama-quantize...")
    print(f"       {f16_path.name} → {q_path.name}")
    result = subprocess.run(
        [binary, str(f16_path), str(q_path), llama_quant_type],
        text=True,
    )
    if result.returncode != 0:
        print(f"  WARNING: llama-quantize failed (rc={result.returncode}) — using F16 GGUF instead.")
        return f16_path

    size_gb = q_path.stat().st_size / 1e9
    print(f"  ✓ Quantized GGUF: {q_path}  ({size_gb:.1f} GB)")
    return q_path


# ─────────────────────────────────────────────────────────────────────────────
#  Steps 6+7 — Modelfile + ollama create
# ─────────────────────────────────────────────────────────────────────────────

def create_ollama_model(gguf_path: Path, model_name: str):
    """Register gguf_path with Ollama under model_name."""
    modelfile_path = gguf_path.with_suffix(".Modelfile")

    modelfile = f"""FROM {gguf_path.as_posix()}

SYSTEM \"\"\"{_SYSTEM_PROMPT}\"\"\"

PARAMETER temperature 0.1
PARAMETER top_p 0.9
PARAMETER num_ctx 4096
PARAMETER stop "<|eot_id|>"
PARAMETER stop "<|end_of_text|>"
"""
    print(f"\n[6/7] Writing Modelfile → {modelfile_path}")
    modelfile_path.write_text(modelfile, encoding="utf-8")

    print(f"\n[7/7] Registering '{model_name}' with Ollama...")
    result = subprocess.run(
        ["ollama", "create", model_name, "-f", str(modelfile_path)],
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ollama create failed (rc={result.returncode})")

    print(f"""
{'=' * 60}
✅  apex-trader is live in Ollama!

Quick test:
  ollama run {model_name} "Symbol: XAUUSD | Direction: BUY | Score: 7.5"

Bot config (dashboard → Settings → LLM):
  OLLAMA_MODEL={model_name}
{'=' * 60}
""")


# ─────────────────────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Merge LoRA adapters + convert to GGUF + deploy to Ollama"
    )
    parser.add_argument("--adapter",    default="lora_output",
                        help="LoRA adapter folder  (default: lora_output)")
    parser.add_argument("--merged",     default="models/apex_trading_model_merged",
                        help="Merged HF model output dir")
    parser.add_argument("--gguf",       default="models/apex-trader.gguf",
                        help="GGUF output path")
    parser.add_argument("--name",       default="apex-trader",
                        help="Ollama model name (default: apex-trader)")
    parser.add_argument("--quant",      default="q4_k_m",
                        choices=["q4_k_m", "q5_k_m", "q8_0", "f16"],
                        help="GGUF quantisation (default: q4_k_m)")
    parser.add_argument("--skip-merge", action="store_true",
                        help="Skip merge step if merged model already exists")
    parser.add_argument("--skip-convert", action="store_true",
                        help="Skip GGUF conversion if .gguf already exists")
    args = parser.parse_args()

    adapter_path = (ROOT / args.adapter).resolve()
    merged_path  = (ROOT / args.merged).resolve()
    gguf_path    = (ROOT / args.gguf).resolve()

    if not adapter_path.exists():
        print(f"ERROR: Adapter path not found: {adapter_path}")
        sys.exit(1)

    print("=" * 60)
    print("APEX  LoRA → GGUF → Ollama  Pipeline")
    print(f"  Adapter : {adapter_path}")
    print(f"  Merged  : {merged_path}")
    print(f"  GGUF    : {gguf_path}")
    print(f"  Model   : {args.name}  [{args.quant.upper()}]")
    print("=" * 60)

    ensure_deps()
    base_model = patch_adapter_config(adapter_path)

    # Step 3 — merge
    merged_has_weights = merged_path.exists() and any(merged_path.glob("*.safetensors"))
    if args.skip_merge and merged_has_weights:
        print(f"\n[3/7] Skipping merge — found existing weights in {merged_path}")
    else:
        merge_lora(adapter_path, base_model, merged_path)

    # Step 4 — convert script
    get_convert_script()

    # Step 5 — GGUF conversion (always produces F16 for q4_k_m/q5_k_m)
    if args.skip_convert and gguf_path.exists():
        print(f"\n[5/7] Skipping conversion — using existing {gguf_path}")
    else:
        convert_to_gguf(merged_path, gguf_path, args.quant)

    # Step 5b — Optional quantization via llama-quantize
    final_gguf = quantize_gguf(gguf_path, args.quant)

    # Steps 6+7 — Ollama
    create_ollama_model(final_gguf, args.name)


if __name__ == "__main__":
    main()

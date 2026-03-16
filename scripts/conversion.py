"""
APEX Bot — GGUF Conversion + Ollama Model Registration
Converts a fine-tuned HuggingFace model to GGUF format (q4_k_m quantization)
and loads it into Ollama as the 'apex-trader' model.

Prerequisites:
  git clone https://github.com/ggerganov/llama.cpp (done automatically)
  pip install -r llama.cpp/requirements.txt

Usage:
  python scripts/conversion.py
  python scripts/conversion.py --model models/apex_trading_model_merged
  python scripts/conversion.py --quant q8_0   # higher quality, larger file
  python scripts/conversion.py --skip-clone    # if llama.cpp already exists
"""
from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import settings as _settings

LLAMA_CPP_DIR = Path("llama.cpp")
MODELFILE_PATH = Path("Modelfile")

SYSTEM_PROMPT = """\
You are APEX, an expert algorithmic trading analyst specializing in:
- Gold (XAUUSD) using Smart Money Concepts (Order Blocks, Fair Value Gaps)
- Macro analysis via DXY (USD Index) and US Treasury yields (US10Y)
- Multi-timeframe technical analysis (M15, H1, H4)

Your decisions must always be structured and data-driven:
1. A clear DECISION: APPROVE or REJECT
2. CONFIDENCE: 0.00–1.00
3. Numbered REASONING covering trend, momentum, macro, sentiment, and calendar
4. For approved trades: ENTRY, STOP_LOSS, TAKE_PROFIT prices and RISK_REWARD ratio

You are conservative. You prefer NO TRADE over a low-quality setup.
Always respect:
- News blackout windows (HIGH impact: 15 min before / 30 min after)
- SEVERE RISK_OFF macro veto (DXY > +0.8% in single session = no trades)
- Minimum signal score thresholds per market regime
"""


def run(cmd: str, cwd: Path | None = None, check: bool = True) -> int:
    """Run a shell command, streaming output to console."""
    print(f"  $ {cmd}")
    result = subprocess.run(
        cmd, shell=True, cwd=str(cwd) if cwd else None
    )
    if check and result.returncode != 0:
        print(f"ERROR: Command failed (exit {result.returncode}): {cmd}")
        sys.exit(result.returncode)
    return result.returncode


def clone_llama_cpp(skip_if_exists: bool = True):
    """Clone the llama.cpp repository and install Python dependencies."""
    if LLAMA_CPP_DIR.exists() and skip_if_exists:
        print(f"  llama.cpp already exists at {LLAMA_CPP_DIR} — skipping clone")
        return

    print("Cloning llama.cpp...")
    run("git clone https://github.com/ggerganov/llama.cpp")

    print("Installing llama.cpp Python requirements...")
    run(f"pip install -r requirements.txt", cwd=LLAMA_CPP_DIR)


def convert_to_gguf(
    model_dir: Path,
    output_path: Path,
    quant_type: str = "q4_k_m",
) -> bool:
    """
    Convert a HuggingFace model directory to GGUF format.
    quant_type: q4_k_m (recommended), q8_0 (higher quality), f16 (no quantization)
    """
    if not model_dir.exists():
        print(f"ERROR: Model directory not found: {model_dir}")
        print(f"  Run: python scripts/fine_tune.py first")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Prefer convert_hf_to_gguf.py (newer llama.cpp) over convert.py (older)
    converter = LLAMA_CPP_DIR / "convert_hf_to_gguf.py"
    if not converter.exists():
        converter = LLAMA_CPP_DIR / "convert.py"
    if not converter.exists():
        print("ERROR: llama.cpp converter not found. Run --clone first.")
        return False

    print(f"\nConverting to GGUF ({quant_type})...")
    print(f"  Input : {model_dir}")
    print(f"  Output: {output_path}")

    cmd = (
        f"python {converter} {model_dir.resolve()} "
        f"--outfile {output_path.resolve()} "
        f"--outtype {quant_type}"
    )
    rc = run(cmd, check=False)
    if rc != 0:
        print("  Conversion failed. Check that the model directory contains model weights.")
        return False

    size_mb = output_path.stat().st_size / 1e6
    print(f"  GGUF file: {output_path} ({size_mb:.0f} MB)")
    return True


def write_modelfile(gguf_path: Path, modelfile_path: Path = MODELFILE_PATH):
    """Write the Ollama Modelfile for the fine-tuned APEX model."""
    # Use absolute path in Modelfile so ollama can find it from any directory
    from_path = str(gguf_path.resolve()).replace("\\", "/")

    content = f"""FROM {from_path}

SYSTEM \"\"\"
{SYSTEM_PROMPT.strip()}
\"\"\"

PARAMETER temperature 0.1
PARAMETER top_p 0.9
PARAMETER num_ctx 4096
PARAMETER repeat_penalty 1.1
"""
    modelfile_path.write_text(content, encoding="utf-8")
    print(f"\nModelfile written: {modelfile_path}")
    return modelfile_path


def load_into_ollama(modelfile_path: Path, model_name: str = "apex-trader") -> bool:
    """Register the GGUF model with Ollama."""
    # Check ollama is available
    rc = run("ollama --version", check=False)
    if rc != 0:
        print("\nERROR: Ollama not found. Install from https://ollama.ai")
        print(f"  Then run manually: ollama create {model_name} -f {modelfile_path}")
        return False

    print(f"\nLoading into Ollama as '{model_name}'...")
    rc = run(f"ollama create {model_name} -f {modelfile_path}", check=False)
    if rc != 0:
        print(f"  ERROR: ollama create failed.")
        print(f"  Try manually: ollama create {model_name} -f {modelfile_path}")
        return False

    print(f"  Model '{model_name}' registered successfully")
    return True


def test_ollama_model(model_name: str = "apex-trader"):
    """Quick smoke test — confirm the model responds."""
    prompt = (
        "Symbol: XAUUSD | Direction: BUY | Score: 8.0 | RSI: 57 | ADX: 29 | "
        "DXY change: -0.2% | US10Y change: -3bps | Macro: RISK_ON. "
        "Should we trade?"
    )
    print(f"\nTesting '{model_name}'...")
    rc = run(f'ollama run {model_name} "{prompt}"', check=False)
    if rc != 0:
        print(f"  Test failed. Check ollama is running: ollama serve")
    else:
        print("  Model responding correctly")


# ─────────────────────────────────────────────────────────────────────────────

def merge_adapters_locally(adapter_dir: Path, output_dir: Path) -> bool:
    """Merge LoRA adapters into the base model and save as float16.

    Reads base_model_name_or_path from adapter_config.json and downloads
    the model from HuggingFace if not cached (~8-16 GB first time).
    Returns True on success.
    """
    import json as _json
    adapter_cfg_path = adapter_dir / "adapter_config.json"
    if not adapter_cfg_path.exists():
        print(f"ERROR: adapter_config.json not found in {adapter_dir}")
        return False

    adapter_cfg = _json.loads(adapter_cfg_path.read_text(encoding="utf-8"))
    base_model_name = adapter_cfg.get("base_model_name_or_path", "unsloth/llama-3.1-8b-bnb-4bit")
    print(f"\n[Merge] Base model   : {base_model_name}")
    print(f"[Merge] Adapter dir  : {adapter_dir}")
    print(f"[Merge] Output dir   : {output_dir}")
    print("[Merge] NOTE: base model will be downloaded from HuggingFace if not cached (~8 GB)")

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        from peft import PeftModel
    except ImportError as e:
        print(f"ERROR: Missing dependency — {e}. Run: pip install transformers peft")
        return False

    has_cuda = torch.cuda.is_available()
    print(f"[Merge] CUDA available: {has_cuda}")

    # Load base model.
    # - With CUDA: load bnb-4bit models using BitsAndBytesConfig (fast, low VRAM).
    # - Without CUDA (CPU-only): skip BitsAndBytesConfig entirely; load as float32
    #   so merge_and_unload() can dequantise in pure PyTorch.
    #   Warning: requires ~30 GB RAM for an 8B model.
    try:
        if "bnb-4bit" in base_model_name and has_cuda:
            print("[Merge] Loading pre-quantised 4-bit model (GPU — will dequantise on merge)...")
            bnb_cfg = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
            )
            base = AutoModelForCausalLM.from_pretrained(
                base_model_name,
                quantization_config=bnb_cfg,
                device_map="auto",
                trust_remote_code=True,
            )
        elif "bnb-4bit" in base_model_name and not has_cuda:
            # Kaggle trained with unsloth/llama-3.1-8b-bnb-4bit but we have no GPU.
            # Map to the unsloth public fp16 mirror (no HuggingFace gating required).
            _UNSLOTH_TO_HF = {
                "unsloth/llama-3.1-8b-bnb-4bit":         "unsloth/Meta-Llama-3.1-8B",
                "unsloth/llama-3.2-3b-bnb-4bit":         "unsloth/Llama-3.2-3B",
                "unsloth/llama-3.2-1b-bnb-4bit":         "unsloth/Llama-3.2-1B",
                "unsloth/mistral-7b-v0.3-bnb-4bit":      "mistralai/Mistral-7B-v0.3",
                "unsloth/gemma-2-9b-bnb-4bit":           "google/gemma-2-9b",
            }
            cpu_model_name = _UNSLOTH_TO_HF.get(base_model_name,
                                                  base_model_name.replace("-bnb-4bit", ""))
            print(f"[Merge] No GPU — loading CPU-compatible variant: {cpu_model_name}")
            print("[Merge] NOTE: CPU merge requires ~30 GB RAM and may take 10-30 min")
            base = AutoModelForCausalLM.from_pretrained(
                cpu_model_name,
                torch_dtype=torch.float32,
                device_map="cpu",
                trust_remote_code=True,
            )
            # Patch adapter config so PEFT finds the right base model
            import json as _json2
            cfg = _json2.loads(adapter_cfg_path.read_text(encoding="utf-8"))
            cfg["base_model_name_or_path"] = cpu_model_name
            adapter_cfg_path.write_text(_json2.dumps(cfg, indent=2), encoding="utf-8")
            print(f"[Merge] Patched adapter_config.json → base_model: {cpu_model_name}")
        else:
            print("[Merge] Loading float16 base model...")
            base = AutoModelForCausalLM.from_pretrained(
                base_model_name,
                torch_dtype=torch.float16,
                device_map="auto",
                trust_remote_code=True,
            )
    except Exception as e:
        print(f"ERROR loading base model '{base_model_name}': {e}")
        return False

    # Use the (possibly patched) adapter config to resolve the actual base name
    try:
        import json as _json3
        _effective_base = _json3.loads(adapter_cfg_path.read_text(encoding="utf-8")).get(
            "base_model_name_or_path", base_model_name
        )
    except Exception:
        _effective_base = base_model_name

    try:
        tokenizer = AutoTokenizer.from_pretrained(_effective_base, trust_remote_code=True)
    except Exception as e:
        print(f"WARNING: tokenizer load failed ({e}), using adapter tokenizer")
        tokenizer = AutoTokenizer.from_pretrained(str(adapter_dir), trust_remote_code=True)

    print("[Merge] Applying LoRA adapters and merging...")
    try:
        merged = PeftModel.from_pretrained(base, str(adapter_dir))
        merged = merged.merge_and_unload()
    except Exception as e:
        print(f"ERROR merging adapters: {e}")
        return False

    print(f"[Merge] Saving merged float16 model → {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(str(output_dir), safe_serialization=True)
    tokenizer.save_pretrained(str(output_dir))
    size_gb = sum(p.stat().st_size for p in output_dir.rglob("*") if p.is_file()) / 1e9
    print(f"[Merge] Done — {size_gb:.1f} GB written to {output_dir}")
    return True


def _has_weights(d: Path) -> bool:
    """Return True if directory contains actual model weight files."""
    return bool(
        list(d.glob("*.safetensors"))
        or list(d.glob("pytorch_model*.bin"))
        or list(d.glob("model-*.safetensors"))
    )


def find_model_paths(model_output_dir: str) -> tuple:
    """Search multiple locations for merged model and LoRA adapter directory.

    Returns (merged_path | None, adapter_path | None).
    Merged path is only returned when it has actual weight files.
    """
    base = Path(model_output_dir)
    name = base.name  # "apex_trading_model"

    merged_candidates = [
        Path(model_output_dir + "_merged"),   # expected: models/apex_trading_model_merged
        base / (name + "_merged"),            # Kaggle: models/apex_trading_model/apex_trading_model_merged
        base / "merged_model",               # alternative
        base / "apex_trading_model_merged",  # Kaggle v2
    ]
    adapter_candidates = [
        base,                                # local fine_tune.py output
        base / name,                         # Kaggle: models/apex_trading_model/apex_trading_model
        base / "lora_adapters",
        base / "apex_trading_model",         # Kaggle v2
    ]

    merged_path = next(
        (p for p in merged_candidates if p.exists() and _has_weights(p)), None
    )
    adapter_path = next(
        (p for p in adapter_candidates if p.exists() and (p / "adapter_config.json").exists()), None
    )
    return merged_path, adapter_path


# ─────────────────────────────────────────────────────────────────────────────

def main():
    tr = _settings.training
    default_model  = str(Path(tr.model_output_dir)) + "_merged"
    default_output = tr.gguf_output

    parser = argparse.ArgumentParser(
        description="Convert fine-tuned model to GGUF for Ollama (defaults from settings.training)"
    )
    parser.add_argument(
        "--model", default=None,
        help=f"Path to merged HuggingFace model directory (default: {default_model})"
    )
    parser.add_argument(
        "--output", default=None,
        help=f"Output GGUF file path (default: {default_output})"
    )
    parser.add_argument(
        "--quant", default=None,
        choices=["q4_k_m", "q8_0", "q5_k_m", "f16"],
        help=f"Quantization type (default: {tr.quant_type})"
    )
    parser.add_argument(
        "--name", default=None,
        help=f"Ollama model name to register (default: {tr.ollama_model_name})"
    )
    parser.add_argument(
        "--skip-clone", action="store_true",
        help="Skip cloning llama.cpp (use existing)"
    )
    parser.add_argument(
        "--skip-ollama", action="store_true",
        help="Skip loading into Ollama (GGUF only)"
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Run a quick smoke test after loading"
    )
    args = parser.parse_args()

    # Resolve effective values (CLI arg > settings.training default)
    model_dir   = Path(args.model  or default_model)
    output_path = Path(args.output or default_output)
    quant       = args.quant or tr.quant_type
    model_name  = args.name  or tr.ollama_model_name

    print(f"\n{'='*60}")
    print("APEX GGUF Conversion Pipeline")
    print(f"  (defaults from settings.training — configure via /api/training/config)")
    print(f"{'='*60}")
    print(f"Model dir : {model_dir}")
    print(f"Output    : {output_path}")
    print(f"Quantize  : {quant}")
    print(f"Ollama    : {model_name}")

    # Step 1: llama.cpp
    print("\n[Step 1] Preparing llama.cpp...")
    clone_llama_cpp(skip_if_exists=args.skip_clone)

    # Step 2: Convert to GGUF
    print("\n[Step 2] Converting to GGUF...")
    success = convert_to_gguf(model_dir, output_path, quant_type=quant)
    if not success:
        sys.exit(1)

    # Step 3: Write Modelfile
    print("\n[Step 3] Writing Modelfile...")
    modelfile = write_modelfile(output_path)

    # Step 4: Load into Ollama
    if not args.skip_ollama:
        print("\n[Step 4] Loading into Ollama...")
        load_into_ollama(modelfile, model_name=model_name)
    else:
        print("\n[Step 4] Skipped — load manually:")
        print(f"  ollama create {model_name} -f {modelfile}")

    # Step 5: Test
    if args.test and not args.skip_ollama:
        test_ollama_model(model_name)

    print(f"\n{'='*60}")
    print("Conversion complete!")
    print(f"  GGUF     : {output_path}")
    print(f"  Modelfile: {modelfile}")
    print(f"\nOllama model '{model_name}' is ready.")
    print(f"  Test: ollama run {model_name}")
    print(f"\nIn .env, set: OLLAMA_MODEL={model_name}")
    print("The bot will now use your fine-tuned model as Tier 1 LLM.")


if __name__ == "__main__":
    main()

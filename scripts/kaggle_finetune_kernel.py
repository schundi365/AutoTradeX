"""
APEX Bot — Kaggle Fine-Tuning Kernel
Uses standard transformers + PEFT + TRL (no unsloth) for broad GPU compatibility.
This script runs INSIDE a Kaggle notebook kernel.
It is uploaded by run_remote_training.py alongside the training JSONL.

Config is injected via environment variables set in kaggle_runner.py.
Output (LoRA adapters + merged 16-bit model) is saved to /kaggle/working/.
"""
import os
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
import subprocess
import sys

# ── Install dependencies ──────────────────────────────────────────────────────
# We do NOT install torch — use Kaggle's pre-installed torch to avoid CUDA
# kernel/compute-capability mismatches (e.g. T4 sm_75 vs pre-built sm_89).
print("Installing fine-tuning dependencies (skipping torch)...")
result = subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q",
     "trl>=0.8", "transformers>=4.40", "accelerate>=0.27",
     "bitsandbytes>=0.43", "datasets>=2.18", "peft>=0.10"],
    check=False,
    capture_output=True,
    text=True,
)
# pip may exit non-zero due to Kaggle's pre-installed resolver conflicts but
# packages are still installed — log and continue.
if result.stdout:
    print(result.stdout[-3000:])
if result.stderr:
    # Only print last 1000 chars — resolver warnings can be verbose
    print(result.stderr[-1000:])
if result.returncode != 0:
    print(f"  WARNING: pip exited {result.returncode} (likely resolver conflicts — continuing)")
print("Dependencies ready.")

# ── Config from env vars (injected by kaggle_runner.py) ─────────────────────
BASE_MODEL      = os.environ.get("APEX_BASE_MODEL",      "unsloth/llama-3.1-8b-bnb-4bit")
MAX_SEQ_LEN     = int(os.environ.get("APEX_MAX_SEQ_LEN",  "512"))   # 512 is enough for GO/NOGO prompts; halves attention memory vs 1024
LORA_RANK       = int(os.environ.get("APEX_LORA_RANK",    "8"))
LORA_ALPHA      = int(os.environ.get("APEX_LORA_ALPHA",   "16"))
NUM_EPOCHS      = int(os.environ.get("APEX_NUM_EPOCHS",   "1"))
BATCH_SIZE      = int(os.environ.get("APEX_BATCH_SIZE",   "1"))     # 1 to avoid T4 VRAM OOM; use grad_accum to compensate
GRAD_ACCUM      = int(os.environ.get("APEX_GRAD_ACCUM",   "8"))     # effective batch = 8 (same as before: 2*4)
SKIP_MERGE      = os.environ.get("APEX_SKIP_MERGE", "0") == "1"     # set to 1 to skip fp16 merge (saves ~16GB RAM)
LEARNING_RATE   = float(os.environ.get("APEX_LEARNING_RATE", "2e-4"))
# Training data written to /kaggle/working/ by the embedded base64 block
TRAIN_FILE      = os.environ.get("APEX_TRAIN_FILE",   "/kaggle/working/apex_training_latest.jsonl")
OUTPUT_DIR      = os.environ.get("APEX_OUTPUT_DIR",  "/kaggle/working/apex_trading_model")
MERGED_DIR      = os.environ.get("APEX_MERGED_DIR",  "/kaggle/working/apex_trading_model_merged")

import gc
import pathlib
import torch

print(f"\n{'='*60}")
print("APEX QLoRA Fine-Tuning on Kaggle GPU")
print(f"  Base model     : {BASE_MODEL}")
print(f"  Training file  : {TRAIN_FILE}")
print(f"  max_seq_length : {MAX_SEQ_LEN}")
print(f"  LoRA rank/alpha: {LORA_RANK}/{LORA_ALPHA}")
print(f"  Epochs/batch   : {NUM_EPOCHS}/{BATCH_SIZE} (grad_accum={GRAD_ACCUM})")
if torch.cuda.is_available():
    gpu = torch.cuda.get_device_properties(0)
    print(f"  GPU            : {gpu.name} ({gpu.total_memory / 1e9:.1f} GB)")
else:
    print("  GPU            : Not available (running on CPU — will be slow)")
print(f"{'='*60}\n")

# ── Verify training data ──────────────────────────────────────────────────────
train_path = pathlib.Path(TRAIN_FILE)
if not train_path.exists():
    print(f"ERROR: Training file not found at {TRAIN_FILE}")
    print(f"  /kaggle/working contents: {list(pathlib.Path('/kaggle/working').iterdir())}")
    sys.exit(1)

line_count = sum(1 for _ in open(TRAIN_FILE))
print(f"Training examples: {line_count}")
if line_count < 1:
    print("ERROR: No training examples found.")
    sys.exit(1)

# ── Load tokenizer ────────────────────────────────────────────────────────────
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, TaskType, prepare_model_for_kbit_training
from trl import SFTTrainer
from datasets import load_dataset

print(f"Loading tokenizer: {BASE_MODEL}")
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token
tokenizer.padding_side = "right"

# ── Load model (4-bit quantization via bitsandbytes) ─────────────────────────
# Note: unsloth/llama-3.1-8b-bnb-4bit is already pre-quantized; we load it
# without an extra bnb config to avoid double-quantization.
print(f"Loading base model: {BASE_MODEL}")
try:
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        device_map="auto",
        torch_dtype=torch.float16,
        trust_remote_code=True,
    )
    print("  Loaded pre-quantized model (no extra BnB config)")
except Exception as e:
    print(f"  Pre-quantized load failed ({e}), falling back to 4-bit BnB config")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
torch.cuda.empty_cache()

model.config.use_cache = False
model.config.pretraining_tp = 1

# Prepare for k-bit training (enables gradient checkpointing + casts LN)
model = prepare_model_for_kbit_training(model)

# ── Apply LoRA ────────────────────────────────────────────────────────────────
print(f"Applying LoRA (rank={LORA_RANK}, alpha={LORA_ALPHA})...")
lora_config = LoraConfig(
    r=LORA_RANK,
    lora_alpha=LORA_ALPHA,
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
    lora_dropout=0.05,
    bias="none",
    task_type=TaskType.CAUSAL_LM,
)
model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

# ── Dataset ───────────────────────────────────────────────────────────────────
PROMPT_TEMPLATE = """### Instruction:
{instruction}

### Input:
{input}

### Response:
{output}"""

dataset = load_dataset("json", data_files=TRAIN_FILE, split="train")

def format_prompts(examples):
    texts = []
    for inst, inp, out in zip(
        examples.get("instruction", [""] * len(examples["text"]) if "text" in examples else []),
        examples.get("input",       [""] * len(examples.get("instruction", []))),
        examples.get("output",      [""] * len(examples.get("instruction", []))),
    ):
        texts.append(
            PROMPT_TEMPLATE.format(instruction=inst, input=inp, output=out)
            + tokenizer.eos_token
        )
    return {"text": texts}

# If data already has "text" field, use directly; otherwise format it
if "instruction" in dataset.column_names:
    dataset = dataset.map(format_prompts, batched=True)
    print(f"Dataset formatted: {len(dataset)} examples")
elif "text" in dataset.column_names:
    print(f"Dataset (pre-formatted text field): {len(dataset)} examples")
else:
    print(f"ERROR: Dataset has neither 'instruction' nor 'text' columns. Columns: {dataset.column_names}")
    sys.exit(1)

# ── Training ──────────────────────────────────────────────────────────────────
use_bf16 = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
use_fp16 = torch.cuda.is_available() and not use_bf16

import inspect as _inspect
import trl as _trl_mod
from transformers import TrainingArguments
print(f"TRL version: {_trl_mod.__version__}")

# Set sequence length on tokenizer — works regardless of TRL version
tokenizer.model_max_length = MAX_SEQ_LEN

# Detect what SFTTrainer.__init__ accepts (varies across TRL versions)
_trainer_params = set(_inspect.signature(SFTTrainer.__init__).parameters)
_use_processing_class = "processing_class" in _trainer_params  # TRL >= 0.12
_trainer_has_packing  = "packing"           in _trainer_params  # TRL < 0.12

_common_args = dict(
    output_dir="/kaggle/working/checkpoints",
    num_train_epochs=NUM_EPOCHS,
    per_device_train_batch_size=BATCH_SIZE,
    gradient_accumulation_steps=GRAD_ACCUM,
    warmup_steps=max(5, line_count // 20),
    learning_rate=LEARNING_RATE,
    fp16=use_fp16, bf16=use_bf16,
    logging_steps=5,
    save_strategy="epoch", save_total_limit=1,
    optim="paged_adamw_8bit", weight_decay=0.01,
    lr_scheduler_type="linear", seed=42, report_to="none",
    gradient_checkpointing=True,  # Crucial for memory saving
)

# Try SFTConfig first (TRL >= 0.8) — it carries packing/dataset_text_field
training_args = None
try:
    from trl import SFTConfig as _SFTConfig
    _sft_fields = set(getattr(_SFTConfig, "__dataclass_fields__", {}).keys())
    _sft_extras = {"packing": False, "dataset_text_field": "text"}
    if "max_seq_length" in _sft_fields:
        _sft_extras["max_seq_length"] = MAX_SEQ_LEN
    training_args = _SFTConfig(**_common_args, **_sft_extras)
    print(f"Using SFTConfig with fields: {sorted(_sft_extras)}")
except Exception as _e:
    print(f"SFTConfig failed ({_e}), falling back to TrainingArguments")
    training_args = TrainingArguments(**_common_args)

# Build SFTTrainer kwargs dynamically so they match the installed TRL version
_tkwargs = {"model": model, "train_dataset": dataset, "args": training_args}

# tokenizer / processing_class
if _use_processing_class:
    _tkwargs["processing_class"] = tokenizer   # TRL >= 0.12
else:
    _tkwargs["tokenizer"] = tokenizer          # TRL < 0.12

# packing / dataset_text_field / max_seq_length (only if SFTTrainer still owns them)
if _trainer_has_packing:
    _tkwargs["packing"]            = False
    _tkwargs["dataset_text_field"] = "text"
    _tkwargs["max_seq_length"]     = MAX_SEQ_LEN

print(f"SFTTrainer kwargs: {sorted(_tkwargs)}")
trainer = SFTTrainer(**_tkwargs)

print(f"\nStarting fine-tuning: {NUM_EPOCHS} epoch(s), packing=False, {'bf16' if use_bf16 else 'fp16'}...")
torch.cuda.empty_cache()
stats = trainer.train()
print(f"\nTraining complete!")
print(f"  Runtime   : {stats.metrics.get('train_runtime', 0):.0f}s")
print(f"  Train loss: {stats.metrics.get('train_loss', 0):.4f}")

# ── Save LoRA adapters ────────────────────────────────────────────────────────
print(f"\nSaving LoRA adapters to {OUTPUT_DIR}...")
model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)
print("LoRA adapters saved.")

# ── Merge adapters into 16-bit model ─────────────────────────────────────────
# The training model is 4-bit quantized — merge_and_unload() on a bnb-4bit model
# silently fails. Fix: free GPU memory, then load the fp16 (non-quantized) base.
# Skip merge if SKIP_MERGE=1 (saves ~16GB RAM; GGUF step will also be skipped).
if SKIP_MERGE:
    print("\nSkipping merge step (APEX_SKIP_MERGE=1). LoRA adapters only.")
else:
    print(f"\nAttempting to merge LoRA into 16-bit model at {MERGED_DIR}...")

    # Map bnb-4bit model IDs → their standard fp16 equivalents on HuggingFace
    _BNB_TO_FP16 = {
        "unsloth/llama-3.1-8b-bnb-4bit":          "unsloth/Meta-Llama-3.1-8B",
        "unsloth/llama-3.1-8b-Instruct-bnb-4bit": "unsloth/Meta-Llama-3.1-8B-Instruct",
        "unsloth/mistral-7b-v0.3-bnb-4bit":       "unsloth/mistral-7b-v0.3",
        "unsloth/gemma-7b-bnb-4bit":              "unsloth/gemma-7b",
        "unsloth/gemma-2-9b-bnb-4bit":            "unsloth/gemma-2-9b",
    }
    _merge_base = _BNB_TO_FP16.get(BASE_MODEL, BASE_MODEL.replace("-bnb-4bit", ""))

    try:
        import traceback
        from peft import PeftModel

        # Free the 4-bit training model + Python garbage before loading fp16
        print("  Freeing training model from GPU/CPU memory...")
        del model
        gc.collect()
        torch.cuda.empty_cache()

        # Load WITHOUT device_map="auto" to avoid accelerate's get_balanced_memory()
        # bug (TypeError: unhashable type: 'set' in accelerate>=0.29 on Python 3.12).
        # Loading to CPU first and performing merge there.
        # Merge on GPU OOMs on 16GB cards for 8B models in FP16.
        print(f"  Loading {_merge_base} in fp16 for merge (DEVICE: CPU)...")
        base_for_merge = AutoModelForCausalLM.from_pretrained(
            _merge_base,
            torch_dtype=torch.float16,
            trust_remote_code=True,
            low_cpu_mem_usage=True,
        )

        # Load adapter without device_map to keep accelerate out of the picture
        merged = PeftModel.from_pretrained(base_for_merge, OUTPUT_DIR, device_map=None)
        merged = merged.merge_and_unload()
        merged.save_pretrained(MERGED_DIR, safe_serialization=True)
        tokenizer.save_pretrained(MERGED_DIR)
        print(f"  Merged model saved to {MERGED_DIR}")

        # Free merged model too — we only need the GGUF
        del merged, base_for_merge
        gc.collect()
        torch.cuda.empty_cache()
    except Exception as e:
        import traceback
        print(f"  WARNING: Merge failed ({type(e).__name__}: {e})")
        traceback.print_exc()
        print("  LoRA adapters are still available — merge locally after download.")

# ── GGUF Conversion (on Kaggle GPU — saves ~4.5 GB file instead of ~15 GB) ───
GGUF_OUTPUT = os.environ.get("APEX_GGUF_OUTPUT", "/kaggle/working/apex_trading_model.gguf")
QUANT_TYPE  = os.environ.get("APEX_QUANT_TYPE",  "q4_k_m")

if SKIP_MERGE:
    print("\nSkipping GGUF conversion (merge was skipped). Download LoRA adapters and convert locally.")
else:

    print(f"\n{'='*60}")
    print(f"GGUF Conversion (target: {QUANT_TYPE})")
    print(f"  Input : {MERGED_DIR}")
    print(f"  Output: {GGUF_OUTPUT}")
    print(f"{'='*60}")

    _merged_ok = pathlib.Path(MERGED_DIR).exists() and any(
        pathlib.Path(MERGED_DIR).glob("*.safetensors")
    )

    if not _merged_ok:
        print("  WARNING: Merged model directory is missing or empty — skipping GGUF conversion.")
        print("  You will need to merge adapters locally after download.")
    else:
        # Step A: Clone llama.cpp (shallow)
        print("\n[GGUF] Cloning llama.cpp...")
        _clone_rc = subprocess.run(
            ["git", "clone", "--depth=1", "https://github.com/ggerganov/llama.cpp", "/kaggle/working/llama.cpp"],
            capture_output=True, text=True,
        ).returncode
        if _clone_rc != 0:
            print("  WARNING: git clone failed — GGUF step skipped.")
        else:
            # Step B: Install llama.cpp Python dependencies
            print("[GGUF] Installing llama.cpp requirements...")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-q", "-r",
                 "/kaggle/working/llama.cpp/requirements.txt"],
                check=False,
            )

            # Step C: Convert merged model → F16 GGUF (pure Python, no compilation needed)
            _f16_gguf = "/kaggle/working/apex_trading_model_f16.gguf"
            _converter = "/kaggle/working/llama.cpp/convert_hf_to_gguf.py"
            if not pathlib.Path(_converter).exists():
                _converter = "/kaggle/working/llama.cpp/convert.py"

            print(f"[GGUF] Converting to F16 GGUF...")
            _conv_rc = subprocess.run(
                [sys.executable, _converter, MERGED_DIR,
                 "--outfile", _f16_gguf, "--outtype", "f16"],
                capture_output=False,
            ).returncode

            if _conv_rc != 0:
                print("  WARNING: F16 conversion failed — GGUF step skipped.")
            else:
                _f16_size_gb = pathlib.Path(_f16_gguf).stat().st_size / 1e9
                print(f"  F16 GGUF: {_f16_gguf} ({_f16_size_gb:.1f} GB)")

                # Step D: Try to compile + use quantize binary for Q4_K_M
                # If compilation fails we fall back to the F16 GGUF.
                _quant_ok = False
                if QUANT_TYPE not in ("f16", "f32"):
                    print(f"[GGUF] Compiling llama.cpp quantize binary (targets {QUANT_TYPE})...")
                    _build_rc = subprocess.run(
                        "cd /kaggle/working/llama.cpp && "
                        "mkdir -p build && cd build && "
                        "cmake .. -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release > /dev/null 2>&1 && "
                        "cmake --build . --config Release --target quantize -- -j$(nproc) 2>&1 | tail -5",
                        shell=True,
                    ).returncode

                    _quantize_bin = "/kaggle/working/llama.cpp/build/bin/quantize"
                    if _build_rc == 0 and pathlib.Path(_quantize_bin).exists():
                        print(f"[GGUF] Quantizing {QUANT_TYPE}...")
                        _qrc = subprocess.run(
                            [_quantize_bin, _f16_gguf, GGUF_OUTPUT, QUANT_TYPE.upper()],
                            capture_output=False,
                        ).returncode
                        if _qrc == 0:
                            _quant_ok = True
                            _q_size_gb = pathlib.Path(GGUF_OUTPUT).stat().st_size / 1e9
                            print(f"  {QUANT_TYPE.upper()} GGUF: {GGUF_OUTPUT} ({_q_size_gb:.1f} GB)")
                            # Remove large F16 to save Kaggle disk
                            pathlib.Path(_f16_gguf).unlink(missing_ok=True)
                            print(f"  Removed F16 intermediate to free space.")
                        else:
                            print(f"  WARNING: quantize returned {_qrc}")
                    else:
                        print(f"  WARNING: Compilation failed (rc={_build_rc}) or binary not found.")

                # Fallback: keep F16 GGUF if quantized failed
                if not _quant_ok:
                    import shutil
                    shutil.copy(_f16_gguf, GGUF_OUTPUT)
                    print(f"  Using F16 GGUF as fallback: {GGUF_OUTPUT}")

                _final_size_gb = pathlib.Path(GGUF_OUTPUT).stat().st_size / 1e9
                print(f"\n  GGUF ready: {GGUF_OUTPUT} ({_final_size_gb:.1f} GB)")
                print(f"  Download this file — load into Ollama with:")
                print(f"    ollama create apex-trader -f Modelfile")

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\nOutputs in /kaggle/working/:")
for p in sorted(pathlib.Path("/kaggle/working").rglob("*")):
    if p.is_file() and "checkpoint" not in str(p) and "llama.cpp" not in str(p):
        print(f"  {p}  ({p.stat().st_size:,} bytes)")

print("\nKaggle fine-tuning complete. Download outputs from the kernel output panel.")

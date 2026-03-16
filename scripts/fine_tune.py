"""
APEX Bot — Fine-Tuning Script
Uses Unsloth + QLoRA for memory-efficient fine-tuning of Llama 3.1 8B.

Hardware requirements:
  - 8B model: 16GB VRAM minimum (RTX 3090 / 4080 / A100)
  - Google Colab Pro (~$10/mo) works for occasional re-training
  - Training time: ~2h on RTX 4090, ~4h on Colab Pro

Install dependencies (NOT part of main requirements.txt — install separately):
  pip install unsloth
  pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
  pip install trl transformers accelerate bitsandbytes

Usage:
  python scripts/fine_tune.py
  python scripts/fine_tune.py --data training_data/apex_training_latest.jsonl
  python scripts/fine_tune.py --epochs 5 --rank 32
  python scripts/fine_tune.py --eval-split 0.1
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import settings as _settings


def check_dependencies():
    missing = []
    for pkg in ["unsloth", "trl", "transformers", "torch"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print("ERROR: Missing fine-tuning dependencies.")
        print(f"  Missing: {', '.join(missing)}")
        print("  Install: pip install unsloth trl transformers accelerate bitsandbytes")
        print("  Colab:   pip install unsloth[colab-new]")
        sys.exit(1)


PROMPT_TEMPLATE = """### Instruction:
{instruction}

### Input:
{input}

### Response:
{output}"""


def format_prompts(examples, tokenizer):
    texts = []
    for inst, inp, out in zip(
        examples["instruction"],
        examples["input"],
        examples["output"],
    ):
        texts.append(
            PROMPT_TEMPLATE.format(instruction=inst, input=inp, output=out)
            + tokenizer.eos_token
        )
    return {"text": texts}


def run_finetuning(
    data_path: str | None = None,
    output_dir: str | None = None,
    base_model: str | None = None,
    max_seq_length: int | None = None,
    lora_rank: int | None = None,
    lora_alpha: int | None = None,
    num_epochs: int | None = None,
    batch_size: int | None = None,
    gradient_accumulation: int | None = None,
    learning_rate: float | None = None,
    eval_split: float | None = None,
    checkpoint_dir: str | None = None,
):
    # Resolve defaults from settings.training (dashboard-configurable)
    tr = _settings.training
    data_path            = data_path            or str(Path(tr.training_data_dir) / "apex_training_latest.jsonl")
    output_dir           = output_dir           or tr.model_output_dir
    base_model           = base_model           or tr.base_model
    max_seq_length       = max_seq_length       if max_seq_length       is not None else tr.max_seq_length
    lora_rank            = lora_rank            if lora_rank            is not None else tr.lora_rank
    lora_alpha           = lora_alpha           if lora_alpha           is not None else tr.lora_alpha
    num_epochs           = num_epochs           if num_epochs           is not None else tr.num_epochs
    batch_size           = batch_size           if batch_size           is not None else tr.batch_size
    gradient_accumulation = gradient_accumulation if gradient_accumulation is not None else tr.gradient_accumulation
    learning_rate        = learning_rate        if learning_rate        is not None else tr.learning_rate
    eval_split           = eval_split           if eval_split           is not None else tr.eval_split
    checkpoint_dir       = checkpoint_dir       or tr.checkpoint_dir

    check_dependencies()

    from unsloth import FastLanguageModel
    from datasets import load_dataset
    from trl import SFTTrainer
    from transformers import TrainingArguments
    import torch

    # ── Verify data ──────────────────────────────────────────────────────────
    data_file = Path(data_path)
    if not data_file.exists():
        print(f"ERROR: Training data not found: {data_path}")
        print("  Run: python scripts/prepare_training_data.py --include-synthetic")
        sys.exit(1)

    line_count = sum(1 for _ in open(data_file))
    print(f"\nTraining data: {data_file} ({line_count} examples)")
    if line_count < 5:
        print("ERROR: Too few examples. Run prepare_training_data.py first.")
        sys.exit(1)

    # ── Load base model ──────────────────────────────────────────────────────
    print(f"Loading base model: {base_model}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=base_model,
        max_seq_length=max_seq_length,
        load_in_4bit=True,
        dtype=None,
    )

    # ── Apply LoRA adapters ──────────────────────────────────────────────────
    print(f"Applying LoRA (rank={lora_rank}, alpha={lora_alpha})...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=lora_rank,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_alpha=lora_alpha,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    # ── Load dataset ─────────────────────────────────────────────────────────
    dataset = load_dataset("json", data_files=str(data_file), split="train")

    if eval_split > 0:
        split = dataset.train_test_split(test_size=eval_split, seed=42)
        train_dataset = split["train"]
        eval_dataset = split["test"]
        print(f"  Train: {len(train_dataset)} | Eval: {len(eval_dataset)}")
    else:
        train_dataset = dataset
        eval_dataset = None
        print(f"  Train: {len(train_dataset)} examples")

    train_dataset = train_dataset.map(
        lambda ex: format_prompts(ex, tokenizer), batched=True
    )
    if eval_dataset:
        eval_dataset = eval_dataset.map(
            lambda ex: format_prompts(ex, tokenizer), batched=True
        )

    # ── Training args ────────────────────────────────────────────────────────
    Path(checkpoint_dir).mkdir(parents=True, exist_ok=True)
    Path(output_dir).parent.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=gradient_accumulation,
        warmup_steps=max(5, line_count // 20),
        num_train_epochs=num_epochs,
        learning_rate=learning_rate,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=10,
        evaluation_strategy="epoch" if eval_dataset else "no",
        save_strategy="epoch",
        output_dir=checkpoint_dir,
        optim="adamw_8bit",
        seed=42,
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        dataset_text_field="text",
        max_seq_length=max_seq_length,
        args=training_args,
    )

    # ── Train ────────────────────────────────────────────────────────────────
    if torch.cuda.is_available():
        gpu = torch.cuda.get_device_properties(0)
        print(f"  GPU: {gpu.name} ({gpu.total_memory / 1e9:.1f} GB VRAM)")
    print(f"\nStarting fine-tuning: {num_epochs} epochs")

    stats = trainer.train()
    print(f"\nTraining complete!")
    print(f"  Runtime   : {stats.metrics.get('train_runtime', 0):.0f}s")
    print(f"  Train loss: {stats.metrics.get('train_loss', 0):.4f}")

    # ── Save adapters + merged ────────────────────────────────────────────────
    print(f"\nSaving LoRA adapters to {output_dir}...")
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    merged_dir = str(output_dir) + "_merged"
    print(f"Saving merged 16-bit model (for GGUF) to {merged_dir}...")
    model.save_pretrained_merged(merged_dir, tokenizer, save_method="merged_16bit")

    print(f"\nNext step: python scripts/conversion.py --model {merged_dir}")
    return output_dir


# ─────────────────────────────────────────────────────────────────────────────

def main():
    tr = _settings.training
    parser = argparse.ArgumentParser(
        description="APEX QLoRA fine-tuning (defaults from settings.training)"
    )
    parser.add_argument("--data",        default=None, help=f"Training JSONL (default: {tr.training_data_dir}/apex_training_latest.jsonl)")
    parser.add_argument("--output",      default=None, help=f"Output dir (default: {tr.model_output_dir})")
    parser.add_argument("--model",       default=None, help=f"Base model (default: {tr.base_model})")
    parser.add_argument("--epochs",      type=int,   default=None, help=f"Epochs (default: {tr.num_epochs})")
    parser.add_argument("--rank",        type=int,   default=None, help=f"LoRA rank (default: {tr.lora_rank})")
    parser.add_argument("--alpha",       type=int,   default=None, help=f"LoRA alpha (default: {tr.lora_alpha})")
    parser.add_argument("--batch",       type=int,   default=None, help=f"Batch size (default: {tr.batch_size})")
    parser.add_argument("--accum",       type=int,   default=None, help=f"Gradient accum steps (default: {tr.gradient_accumulation})")
    parser.add_argument("--lr",          type=float, default=None, help=f"Learning rate (default: {tr.learning_rate})")
    parser.add_argument("--eval-split",  type=float, default=None, help=f"Eval split fraction (default: {tr.eval_split})")
    parser.add_argument("--checkpoints", default=None, help=f"Checkpoint dir (default: {tr.checkpoint_dir})")
    args = parser.parse_args()

    eff_model  = args.model  or tr.base_model
    eff_data   = args.data   or str(Path(tr.training_data_dir) / "apex_training_latest.jsonl")
    eff_epochs = args.epochs if args.epochs is not None else tr.num_epochs
    eff_rank   = args.rank   if args.rank   is not None else tr.lora_rank
    eff_lr     = args.lr     if args.lr     is not None else tr.learning_rate

    print(f"\n{'='*60}")
    print("APEX QLoRA Fine-Tuning Pipeline")
    print(f"{'='*60}")
    print(f"Base model : {eff_model}")
    print(f"Data       : {eff_data}")
    print(f"Epochs     : {eff_epochs} | Rank: {eff_rank} | LR: {eff_lr}")
    print(f"  (configure via dashboard /api/training/config)")

    run_finetuning(
        data_path=args.data,
        output_dir=args.output,
        base_model=args.model,
        lora_rank=args.rank,
        lora_alpha=args.alpha,
        num_epochs=args.epochs,
        batch_size=args.batch,
        gradient_accumulation=args.accum,
        learning_rate=args.lr,
        eval_split=args.eval_split,
        checkpoint_dir=args.checkpoints,
    )


if __name__ == "__main__":
    main()

"""
APEX Bot — Local LoRA Merge Utility
Merges Kaggle-trained adapters into the base FP16 model locally.
Usage: python scripts/manual_merge.py --adapter C:/path/to/lora_folder --output C:/path/to/merged_model
"""
import argparse
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Merge LoRA adapters locally.")
    parser.add_argument("--adapter", type=str, required=True, help="Path to folder containing adapter_model.bin and adapter_config.json")
    parser.add_argument("--base", type=str, default="unsloth/Meta-Llama-3.1-8B-Instruct", help="Base model ID (fp16)")
    parser.add_argument("--output", type=str, required=True, help="Path to save the merged model")
    
    args = parser.parse_args()
    
    adapter_path = Path(args.adapter)
    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)
    
    print(f"Loading base model: {args.base}...")
    # Load in FP16 to the CPU (safer for local RAM)
    base_model = AutoModelForCausalLM.from_pretrained(
        args.base,
        torch_dtype=torch.float16,
        device_map="cpu",
        trust_remote_code=True
    )
    
    print(f"Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(args.base)
    
    print(f"Loading Peft model from {adapter_path}...")
    model = PeftModel.from_pretrained(base_model, str(adapter_path))
    
    print("Merging and unloading...")
    merged_model = model.merge_and_unload()
    
    print(f"Saving merged model to {output_path}...")
    merged_model.save_pretrained(str(output_path))
    tokenizer.save_pretrained(str(output_path))
    
    print("\n✅ Merge complete!")
    print(f"Next steps:")
    print(f"1. Use llama.cpp to convert {output_path} to GGUF.")
    print(f"2. Create a Modelfile and run `ollama create apex-bot -f Modelfile`.")

if __name__ == "__main__":
    main()

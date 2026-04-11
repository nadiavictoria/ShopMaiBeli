"""
SFT training script for ShopMaiBeli workflow generator.

Fine-tunes Qwen2.5-3B-Instruct on (query → workflow JSON) pairs using LoRA.

Usage (on Vast.ai RTX 5080):
    pip install transformers peft trl datasets accelerate bitsandbytes
    python models/train.py \
        --data_dir data/workflows \
        --output_dir models/checkpoints/shopmaibeli-sft \
        --epochs 3

The trained adapter is saved to --output_dir and can be loaded by models/serve.py.
"""

import argparse
import json
import os
import sys

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="SFT fine-tuning for workflow generation")
    parser.add_argument("--base_model", default="Qwen/Qwen2.5-3B-Instruct",
                        help="HuggingFace model ID for the base model")
    parser.add_argument("--data_dir", default="data/workflows",
                        help="Directory containing training JSONL files")
    parser.add_argument("--output_dir", default="models/checkpoints/shopmaibeli-sft",
                        help="Where to save the LoRA adapter")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--batch_size", type=int, default=4)
    parser.add_argument("--grad_accum", type=int, default=4)
    parser.add_argument("--max_seq_len", type=int, default=2048)
    parser.add_argument("--lora_r", type=int, default=64)
    parser.add_argument("--lora_alpha", type=int, default=128)
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------

def load_training_examples(data_dir: str) -> list[dict]:
    """
    Load all .jsonl files from data_dir.

    Each line must be a JSON object with 'instruction' and 'output' keys:
      {"instruction": "Find wireless earbuds under $80", "output": "{...workflow json...}"}
    """
    examples = []
    if not os.path.isdir(data_dir):
        print(f"[train] ERROR: data_dir '{data_dir}' does not exist", file=sys.stderr)
        sys.exit(1)

    for fname in sorted(os.listdir(data_dir)):
        if not fname.endswith(".jsonl"):
            continue
        path = os.path.join(data_dir, fname)
        with open(path, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if "instruction" not in obj or "output" not in obj:
                        print(f"[train] WARNING: {fname}:{lineno} missing 'instruction' or 'output', skipping")
                        continue
                    examples.append(obj)
                except json.JSONDecodeError as e:
                    print(f"[train] WARNING: {fname}:{lineno} JSON parse error: {e}")

    print(f"[train] Loaded {len(examples)} training examples from {data_dir}")
    return examples


def format_prompt(instruction: str, output: str, system_prompt: str) -> str:
    """Format a single training example as a chat-style prompt."""
    return (
        f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
        f"<|im_start|>user\nUser wants to: {instruction}<|im_end|>\n"
        f"<|im_start|>assistant\n{output}<|im_end|>"
    )


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train(args):
    # Lazy imports — not installed locally, only on training machine
    try:
        import torch
        from datasets import Dataset
        from peft import LoraConfig, TaskType, get_peft_model
        from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
        from trl import SFTTrainer
    except ImportError as e:
        print(f"[train] ERROR: Missing dependency: {e}")
        print("[train] Run: pip install transformers peft trl datasets accelerate bitsandbytes")
        sys.exit(1)

    # Load system prompt
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "workflow_gen.txt")
    with open(prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    # Load training data
    raw_examples = load_training_examples(args.data_dir)
    if not raw_examples:
        print("[train] ERROR: No training examples found. Add .jsonl files to data/workflows/")
        sys.exit(1)

    formatted = [
        {"text": format_prompt(ex["instruction"], ex["output"], system_prompt)}
        for ex in raw_examples
    ]
    dataset = Dataset.from_list(formatted)
    print(f"[train] Dataset size: {len(dataset)} examples")

    # Load base model + tokenizer
    print(f"[train] Loading base model: {args.base_model}")
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )

    # LoRA config
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.05,
        bias="none",
        target_modules="all-linear",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Training arguments
    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        bf16=True,
        logging_steps=10,
        save_strategy="epoch",
        save_total_limit=2,
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        args=training_args,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=args.max_seq_len,
    )

    print("[train] Starting training...")
    trainer.train()

    print(f"[train] Saving adapter to {args.output_dir}")
    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)
    print("[train] Done.")


if __name__ == "__main__":
    args = parse_args()
    train(args)

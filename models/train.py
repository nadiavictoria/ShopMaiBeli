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
import random
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
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--strict_validation",
        action="store_true",
        help="Fail fast if a training example has invalid workflow JSON",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------

def _prepare_example(obj: dict, source: str, strict_validation: bool) -> dict | None:
    """
    Parse and validate a single training example.

    Training data is expected to contain current workflow JSON. Older examples
    are normalized where possible so retraining stays aligned with the active
    backend/frontend behavior.
    """
    if "instruction" not in obj or "output" not in obj:
        print(f"[train] WARNING: {source} missing 'instruction' or 'output', skipping")
        return None

    try:
        from backend.workflow_generator import _normalize_report_output, validate_workflow
    except ImportError:
        _normalize_report_output = None
        validate_workflow = None

    try:
        workflow = json.loads(obj["output"])
    except json.JSONDecodeError as e:
        message = f"[train] {'ERROR' if strict_validation else 'WARNING'}: {source} invalid workflow JSON: {e}"
        print(message, file=sys.stderr if strict_validation else sys.stdout)
        if strict_validation:
            sys.exit(1)
        return None

    if _normalize_report_output is not None:
        workflow = _normalize_report_output(workflow)

    if validate_workflow is not None:
        errors = validate_workflow(workflow)
        if errors:
            message = (
                f"[train] {'ERROR' if strict_validation else 'WARNING'}: "
                f"{source} failed validation: {'; '.join(errors)}"
            )
            print(message, file=sys.stderr if strict_validation else sys.stdout)
            if strict_validation:
                sys.exit(1)
            return None

    return {
        "instruction": str(obj["instruction"]).strip(),
        "output": json.dumps(workflow, ensure_ascii=False),
    }


def load_training_examples(data_dir: str, strict_validation: bool = False) -> list[dict]:
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
                    prepared = _prepare_example(obj, f"{fname}:{lineno}", strict_validation)
                    if prepared is not None:
                        examples.append(prepared)
                except json.JSONDecodeError as e:
                    message = (
                        f"[train] {'ERROR' if strict_validation else 'WARNING'}: "
                        f"{fname}:{lineno} JSON parse error: {e}"
                    )
                    print(message, file=sys.stderr if strict_validation else sys.stdout)
                    if strict_validation:
                        sys.exit(1)

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
        from trl import SFTConfig, SFTTrainer
    except ImportError as e:
        print(f"[train] ERROR: Missing dependency: {e}")
        print("[train] Run: pip install transformers peft trl datasets accelerate bitsandbytes")
        sys.exit(1)

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    # Load system prompt
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "workflow_gen.txt")
    with open(prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    # Load training data
    raw_examples = load_training_examples(args.data_dir, strict_validation=args.strict_validation)
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
    training_args = SFTConfig(
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
        dataset_text_field="text",
        max_length=args.max_seq_len,
    )

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        args=training_args,
        train_dataset=dataset,
    )

    print("[train] Starting training...")
    trainer.train()

    print(f"[train] Saving adapter to {args.output_dir}")
    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    os.makedirs(args.output_dir, exist_ok=True)
    metadata = {
        "base_model": args.base_model,
        "data_dir": args.data_dir,
        "epochs": args.epochs,
        "learning_rate": args.lr,
        "batch_size": args.batch_size,
        "gradient_accumulation": args.grad_accum,
        "max_seq_len": args.max_seq_len,
        "lora_r": args.lora_r,
        "lora_alpha": args.lora_alpha,
        "seed": args.seed,
        "num_examples": len(dataset),
    }
    with open(os.path.join(args.output_dir, "training_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print("[train] Done.")


if __name__ == "__main__":
    args = parse_args()
    train(args)

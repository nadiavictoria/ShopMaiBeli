"""
SFT training script for workflow generation model.
Base model: Qwen/Qwen2.5-3B-Instruct
Fine-tuning: LoRA via PEFT + TRL
Run on: Vast.ai RTX 5080

Usage:
    python models/train.py --data_path data/workflows/ --output_dir models/checkpoints/
"""
import argparse
import json
import os
from pathlib import Path


def load_training_data(data_path: str) -> list[dict]:
    examples = []
    for f in Path(data_path).glob("*.jsonl"):
        with open(f) as fp:
            for line in fp:
                line = line.strip()
                if line:
                    examples.append(json.loads(line))
    return examples


def format_prompt(instruction: str) -> str:
    return f"""<|im_start|>system
You are a workflow generator for ShopMaiBeli. Given a shopping request, output a valid n8n Workflow JSON.
<|im_end|>
<|im_start|>user
{instruction}
<|im_end|>
<|im_start|>assistant
"""


def train(args):
    try:
        from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments
        from peft import LoraConfig, get_peft_model
        from trl import SFTTrainer
        from datasets import Dataset
    except ImportError:
        print("Training dependencies not installed. Run: pip install transformers peft trl datasets torch")
        return

    print(f"Loading training data from {args.data_path}...")
    examples = load_training_data(args.data_path)
    print(f"Loaded {len(examples)} examples")

    def format_example(ex):
        prompt = format_prompt(ex["instruction"])
        return {"text": prompt + ex["output"] + "<|im_end|>"}

    dataset = Dataset.from_list([format_example(ex) for ex in examples])

    print(f"Loading base model: {args.model_name}")
    tokenizer = AutoTokenizer.from_pretrained(args.model_name, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.model_name, trust_remote_code=True, torch_dtype="auto", device_map="auto"
    )

    lora_config = LoraConfig(
        r=64,
        lora_alpha=128,
        target_modules="all-linear",
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM"
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        warmup_ratio=0.05,
        lr_scheduler_type="cosine",
        logging_steps=10,
        save_strategy="epoch",
        bf16=True,
        report_to="none"
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=training_args,
        dataset_text_field="text",
        max_seq_length=4096
    )

    print("Starting training...")
    trainer.train()
    trainer.save_model(args.output_dir)
    print(f"Model saved to {args.output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_name", default="Qwen/Qwen2.5-3B-Instruct")
    parser.add_argument("--data_path", default="data/workflows/")
    parser.add_argument("--output_dir", default="models/checkpoints/")
    parser.add_argument("--epochs", type=int, default=3)
    args = parser.parse_args()
    train(args)

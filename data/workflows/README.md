# SFT Training Data

This directory holds supervised fine-tuning (SFT) training data for the ShopMaiBeli workflow generation model.

Each `.jsonl` file contains one training example per line. Each example is a JSON object with:
- `"instruction"`: A prompt describing what the user wants (e.g. `"User wants to: find wireless earbuds under $80"`)
- `"output"`: A complete, valid n8n Workflow JSON string that satisfies the request

These query → workflow pairs are used to fine-tune `Qwen/Qwen2.5-3B-Instruct` via LoRA (see `models/train.py`).

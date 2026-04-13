# Artifacts And Reproducibility

This project is split into:

- source code in GitHub
- large artifacts in Google Drive

Do not commit trained checkpoints or logs to GitHub. Keep them in a local
`artifacts/` folder after downloading from Drive.

## Recommended Local Layout

After cloning the repo, keep large files in this layout:

```text
ShopMaiBeli/
├── artifacts/
│   ├── checkpoints/
│   │   └── shopmaibeli-sft-v3/
│   │       ├── adapter_model.safetensors
│   │       ├── adapter_config.json
│   │       ├── tokenizer.json
│   │       ├── tokenizer_config.json
│   │       ├── special_tokens_map.json
│   │       ├── added_tokens.json
│   │       ├── merges.txt
│   │       ├── vocab.json
│   │       ├── chat_template.jinja
│   │       ├── training_args.bin
│   │       └── training_metadata.json
│   └── logs/
│       └── train-577860.log
├── output/
│   ├── amazon_reviews_sample.json
│   ├── amazon_reviews_sample.csv
│   ├── full_amazon_fashion_review.json
│   ├── full_amazon_fashion_review.csv
│   ├── optional_full_corpus/
│   │   ├── full_amazon_review.json
│   │   └── full_amazon_review.csv
│   └── heldout_sft_queries.txt
```

This keeps the repo clean while making the runtime paths predictable.

## What To Upload To Google Drive

Create a top-level Drive folder like:

```text
ShopMaiBeli_artifacts/
├── checkpoints/
│   └── shopmaibeli-sft-v3/
├── datasets/
│   ├── runtime/
│   │   ├── amazon_reviews_sample.json
│   │   ├── amazon_reviews_sample.csv
│   │   ├── full_amazon_fashion_review.json
│   │   └── full_amazon_fashion_review.csv
│   └── optional_full_corpus/
│       ├── full_amazon_review.json
│       └── full_amazon_review.csv
├── logs/
│   └── train-577860.log
└── optional/
    ├── sft_probe_results_v3b.jsonl
    └── screenshots_or_demo_assets/
```

Upload these files to Drive:

- `shopmaibeli-sft-v3/`
- `train-577860.log`
- `amazon_reviews_sample.json`
- `amazon_reviews_sample.csv`
- `full_amazon_fashion_review.json`
- `full_amazon_fashion_review.csv`

Optional but useful:

- `full_amazon_review.json`
- `full_amazon_review.csv`
- `output/sft_probe_results_v3b.jsonl`
- a short text file containing the Drive folder structure and checkpoint version

## What To Keep In GitHub

Keep these in GitHub:

- all source code
- prompts
- scripts
- training data construction code
- small metadata files
- instructions for downloading artifacts

Do not keep these in GitHub:

- trained checkpoints
- training logs
- large datasets
- local runtime logs

## Download Instructions

1. Clone the repo.
2. Download the artifact folder from Google Drive.
3. Copy the downloaded files into:

```text
artifacts/checkpoints/shopmaibeli-sft-v3/
artifacts/logs/train-577860.log
output/amazon_reviews_sample.json
output/amazon_reviews_sample.csv
output/full_amazon_fashion_review.json
output/full_amazon_fashion_review.csv
```

Optional large corpus files can go in:

```text
output/full_amazon_review.json
output/full_amazon_review.csv
```

The current lightweight RAG prototype only requires:

- `output/amazon_reviews_sample.json`
- `output/full_amazon_fashion_review.json`

The full Amazon review corpus is optional for now and is much larger.

## Running Without The Trained SFT

If you only want the DeepSeek-backed system:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
echo "DEEPSEEK_API_KEY=your-key-here" > backend/.env
./start.sh
```

This uses DeepSeek for workflow generation when `SFT_MODEL_URL` is not set.
It still expects the local review datasets above if you want the review
retrieval path in `ReviewAnalyzer(mode="rag")`.

## Running With The Trained SFT

### 1. Start the SFT server

If the checkpoint is in `artifacts/checkpoints/shopmaibeli-sft-v3/`:

```bash
python models/serve.py \
  --adapter_path artifacts/checkpoints/shopmaibeli-sft-v3 \
  --port 8001
```

`models/serve.py` already includes `--max-lora-rank 64`, so it can load the
trained LoRA adapter.

### 2. Configure the backend

Set `backend/.env` to:

```bash
DEEPSEEK_API_KEY=your-key-here
SFT_MODEL_URL=http://localhost:8001
```

### 3. Start the app

```bash
./start.sh
```

### 4. Verify that SFT is used

In a second terminal:

```bash
tail -n 200 -f backend.log
```

Send a query in the UI and look for:

```text
[generate_workflow] SFT model succeeded
```

## Re-running The Held-Out Probe

After serving the SFT model locally on port `8001`:

```bash
python scripts/probe_sft_outputs.py \
  --base-url http://localhost:8001 \
  --model shopmaibeli-sft \
  --max-tokens 1400 \
  --output output/sft_probe_results_v3b.jsonl
```

This checks:

- raw JSON discipline
- parse success
- workflow schema validity

## Suggested Submission Packaging

For GitHub:

- source code only
- include this artifact guide

For Canvas ZIP:

- source code
- report PDF
- demo video
- optionally include the checkpoint only if the ZIP size limit allows it

If the checkpoint is too large for submission, mention in the report that the
trained adapter and local datasets are distributed separately via Google Drive.

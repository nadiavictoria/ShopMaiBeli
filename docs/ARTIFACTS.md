# Artifacts And Reproducibility

This document reflects the current checked-in code paths, especially:

- `models/train.py`
- `models/serve.py`
- `backend/workflow_generator.py`
- `nodes/review_analyzer.py`
- `scripts/probe_sft_outputs.py`

The repo is intentionally lightweight. Large model outputs, logs, and optional
datasets should live outside Git or under ignored local directories.

## Checked-In Runtime Artifacts

The current repo already references these local runtime files directly:

```text
artifacts/
└── sft_debug/
    ├── latest_raw_response.txt
    └── <timestamp>_raw_response.txt

output/
├── amazon_review_small.csv
├── amazon_review_small.json
├── amazon_reviews_sample.csv
├── amazon_reviews_sample.json
├── full_amazon_fashion_review.csv
├── full_amazon_fashion_review.json
├── full_amazon_review.csv
├── full_amazon_review.json
├── heldout_sft_queries.txt
├── sft_probe_results.jsonl
├── sft_probe_results_v2.jsonl
├── sft_probe_results_v3a.jsonl
└── sft_probe_results_v3b.jsonl
```

The code currently reads these paths by default:

- `backend/workflow_generator.py`
  writes SFT raw-output debug files to `artifacts/sft_debug/`
- `nodes/review_analyzer.py`
  reads `output/full_amazon_fashion_review.json` and
  `output/amazon_reviews_sample.json` by default
- `scripts/probe_sft_outputs.py`
  reads `output/heldout_sft_queries.txt` and writes
  `output/sft_probe_results.jsonl` by default

## Recommended Layout For New Large Artifacts

Keep large, generated, or machine-specific files in this structure:

```text
ShopMaiBeli/
├── artifacts/
│   ├── checkpoints/
│   │   └── shopmaibeli-sft/
│   │       ├── adapter_config.json
│   │       ├── adapter_model.safetensors
│   │       ├── special_tokens_map.json
│   │       ├── tokenizer.json
│   │       ├── tokenizer_config.json
│   │       └── training_metadata.json
│   ├── logs/
│   │   └── train-<jobid>.log
│   └── sft_debug/
│       ├── latest_raw_response.txt
│       └── <timestamp>_raw_response.txt
├── output/
│   ├── amazon_reviews_sample.json
│   ├── full_amazon_fashion_review.json
│   ├── full_amazon_review.json
│   ├── heldout_sft_queries.txt
│   └── sft_probe_results.jsonl
```

Why this layout:

- it matches the current default code paths
- it keeps trained adapters and logs out of normal source control
- it preserves a dedicated place for malformed SFT generations

## What Should Stay In Git

Keep these in the repo:

- source code
- prompt files in `models/prompts/`
- workflow JSON in `workflows/`
- scripts such as `scripts/probe_sft_outputs.py`
- lightweight sample datasets and held-out query lists already tracked in
  `output/`
- documentation describing how to obtain larger artifacts

Do not commit these unless you explicitly want versioned artifacts:

- new training checkpoints
- SLURM logs and other training logs
- duplicated large review corpora
- ad hoc local probe dumps beyond the intended reproducibility set
- raw temporary experiment outputs

## Training Artifact Outputs

`models/train.py` writes the LoRA adapter to the requested `--output_dir`.

Current canonical training command:

```bash
python models/train.py \
  --data_dir data/workflows/train.jsonl \
  --output_dir models/checkpoints/shopmaibeli-sft \
  --epochs 3 \
  --strict_validation \
  --seed 42
```

That output directory should contain at least:

- adapter weights
- tokenizer files
- `training_metadata.json`

If you want the artifact to live outside the repo working tree, prefer a path
under `artifacts/checkpoints/`, for example:

```bash
python models/train.py \
  --data_dir data/workflows/train.jsonl \
  --output_dir artifacts/checkpoints/shopmaibeli-sft \
  --epochs 3 \
  --strict_validation \
  --seed 42
```

## Serving Artifacts

The current serving helper is `models/serve.py`.

Example with an artifact-managed checkpoint:

```bash
python models/serve.py \
  --adapter_path artifacts/checkpoints/shopmaibeli-sft \
  --port 8001
```

Equivalent direct vLLM command:

```bash
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-3B-Instruct \
  --enable-lora \
  --lora-modules shopmaibeli-sft=artifacts/checkpoints/shopmaibeli-sft \
  --max-lora-rank 64 \
  --port 8001 \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.9 \
  --dtype bfloat16 \
  --trust-remote-code
```

The backend expects:

```bash
SFT_MODEL_URL=http://localhost:8001
```

When this path is exercised, malformed or suspicious raw SFT outputs can be
inspected under `artifacts/sft_debug/`.

## Review Corpus Artifacts

`nodes/review_analyzer.py` defaults to:

- `output/full_amazon_fashion_review.json`
- `output/amazon_reviews_sample.json`

If those files are missing, the code logs the absence and falls back to simple
rating-based review summaries.

If you want to override the corpus in a workflow, use node parameters:

- `datasetPath`
- `datasetPaths`

That means reproducibility is best when the exact JSON corpus files used for a
demo or experiment are preserved alongside the checkpoint/log metadata.

## SFT Probe Artifacts

Current probe command:

```bash
python scripts/probe_sft_outputs.py \
  --base-url http://localhost:8001 \
  --model shopmaibeli-sft \
  --output output/sft_probe_results.jsonl
```

By default the script:

- reads held-out prompts from `output/heldout_sft_queries.txt`
- writes line-delimited diagnostics to `output/sft_probe_results.jsonl`
- records parseability, validation status, markdown fences, explanatory text,
  and disallowed node/connection types

If you want to preserve a specific evaluation run, rename the output after the
probe finishes, for example:

```text
output/sft_probe_results_v4.jsonl
```

## Suggested External Storage Layout

For Google Drive or another artifact store, a practical layout is:

```text
ShopMaiBeli_artifacts/
├── checkpoints/
│   └── shopmaibeli-sft/
├── logs/
│   └── train-<jobid>.log
├── probes/
│   ├── sft_probe_results_v3b.jsonl
│   └── sft_probe_results_v4.jsonl
└── datasets/
    ├── amazon_reviews_sample.json
    ├── full_amazon_fashion_review.json
    └── full_amazon_review.json
```

This mirrors the current code assumptions while keeping big files out of Git.

## Reproducing The App Without SFT

DeepSeek-only:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cat > backend/.env <<'EOF'
DEEPSEEK_API_KEY=your-key-here
EOF
./start.sh
```

With no model env vars at all, the backend still runs and falls back to
`workflows/example_shopping.json`.

## Reproducing The App With SFT

1. Serve the adapter on port `8001`.
2. Set:

```bash
cat > backend/.env <<'EOF'
SFT_MODEL_URL=http://localhost:8001
DEEPSEEK_API_KEY=your-key-here
EOF
```

3. Start the app:

```bash
./start.sh
```

4. Confirm the generation path:

```bash
tail -n 100 backend.log
```

Look for:

```text
[generate_workflow] SFT model succeeded
```

And if debugging is needed:

```text
artifacts/sft_debug/latest_raw_response.txt
```

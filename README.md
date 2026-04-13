# ShopMaiBeli — Agentic Shopping Assistant

ShopMaiBeli is an **agentic AI system** that transforms natural language shopping requests into executable workflow graphs, runs them against live product APIs, and returns ranked comparison results.

Instead of returning a simple list of items, the system:
- generates a **workflow graph (DAG)** from a natural language query,
- executes it with **parallel processing and failure recovery**, and
- returns a **structured Markdown comparison report** with review sentiment.

---

## Current Status

| Component | Status | Notes |
|---|---|---|
| Execution Engine | ✅ Complete | Parallel execution, retry logic, streaming NDJSON |
| ProductSearch Node | ✅ Complete | DummyJSON, FakeStoreAPI, mock, plus local `amazon-local` fallback from review corpora |
| ReviewAnalyzer Node | ✅ Complete | Default `rag` mode uses local review JSON corpora; falls back to simple rating-based analysis |
| Agent Node | ✅ Complete | DeepSeek LLM via OpenAI-compatible API |
| ConvertToFile Node | ✅ Complete | Outputs Markdown files and final report payloads |
| Frontend (Chainlit) | ✅ Running | Chat UI with streaming steps and HTML preview rendered separately from step text |
| Backend (FastAPI) | ✅ Running | `/health`, `/get_workflow`, `/run_workflow` |
| Workflow Generation | ✅ Complete | SFT-first generation with DeepSeek fallback and final hardcoded fallback |
| SFT Training Script | ✅ Complete | `models/train.py` — LoRA on Qwen2.5-3B-Instruct with a lean schema-anchored prompt |
| SFT Serving Script | ✅ Complete | `models/serve.py` — vLLM OpenAI-compatible server with `max_lora_rank=64` |
| Training Data | ✅ Complete | `data/workflows/train.jsonl` — curated workflow dataset |
| SFT Model (trained) | ✅ Complete | `shopmaibeli-sft-v3` checkpoint available as an external artifact |

---

## Getting Started

### Prerequisites
- Python 3.12+
- DeepSeek API key (or any OpenAI-compatible LLM key)

### Artifacts

Large artifacts are intentionally kept out of GitHub. See [docs/ARTIFACTS.md](docs/ARTIFACTS.md) for:

- what to upload to Google Drive
- where to place downloaded checkpoints locally
- where to place downloaded local review datasets
- how to run the app with or without the trained SFT adapter

### 1. Clone and Set Up

```bash
git clone <repo-url>
cd ShopMaiBeli
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure API Key

```bash
echo "DEEPSEEK_API_KEY=your-key-here" > backend/.env
```

### 3. Start the Application

```bash
./start.sh
```

This launches:
- **Backend** on http://localhost:8888 (FastAPI)
- **Frontend** on http://localhost:8000 (Chainlit)

### 4. Use the Chat Interface

Visit **http://localhost:8000**, then:
1. In the chat input, type `/` and select **`run_workflow`**
2. Type your shopping query and send, e.g.:
   ```
   find me the best wireless earbuds under $100
   ```

The system will:
1. Generate a workflow JSON via the served SFT model when `SFT_MODEL_URL` is set, otherwise fall back to DeepSeek
2. Execute: ChatTrigger → QueryAnalyzer → ProductSearch → ReviewAnalyzer → ReportGenerator → ConvertToFile
3. Stream step-by-step progress and return a ranked Markdown comparison report

### 5. Stop the Application

```bash
./stop.sh
```

---

## SFT Model Training (GPU Cluster / Vast.ai)

From a fresh clone on the GPU machine:

```bash
# Go into the repo
cd ~/ShopMaiBeli

# Create and activate the cluster venv
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip

# Install CUDA-compatible PyTorch
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# Install training dependencies
python -m pip install transformers peft trl datasets accelerate bitsandbytes sentencepiece

# Verify GPU access
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no gpu')"

# Train on the curated dataset only
python models/train.py \
  --data_dir data/workflows/train.jsonl \
  --output_dir models/checkpoints/shopmaibeli-sft \
  --epochs 3 \
  --strict_validation \
  --seed 42

# Serve the trained adapter
python models/serve.py --adapter_path models/checkpoints/shopmaibeli-sft --port 8001

# Point the backend to the SFT model
echo "SFT_MODEL_URL=http://localhost:8001" >> backend/.env
```

`models/train.py` now validates each training example's workflow JSON against the
current generator schema before training starts and writes
`training_metadata.json` into the checkpoint directory so retraining runs are
traceable.

Important notes:

- The training job should point to `data/workflows/train.jsonl`, not the whole `data/workflows/` directory.
- The directory contains multiple `.jsonl` files, and using the directory would mix in older datasets unintentionally.
- Training order is shuffled by the trainer during training, so the physical line order in `train.jsonl` does not control epoch order.
- The current SFT setup uses the lean prompt at `models/prompts/workflow_gen_sft.txt`.

If you are using Slurm, submit the checked-in [train_sft.slurm](train_sft.slurm):

```bash
sbatch train_sft.slurm
```

Then monitor it with:

```bash
squeue -u $USER
tail -f train-<jobid>.log
```

The workflow generator will automatically use the SFT model when `SFT_MODEL_URL` is set, falling back to DeepSeek API otherwise.

## SFT Evaluation

Held-out probing is built into [scripts/probe_sft_outputs.py](scripts/probe_sft_outputs.py).

With the current `shopmaibeli-sft-v3` setup, the successful evaluation loop used:

```bash
python scripts/probe_sft_outputs.py \
  --base-url http://localhost:8001 \
  --model shopmaibeli-sft \
  --max-tokens 1400 \
  --output output/sft_probe_results_v3b.jsonl
```

The current SFT backend path also uses `max_tokens=1400` to avoid truncating
valid workflow JSON responses.

## Using The Trained Checkpoint

If you downloaded the released adapter artifact from Google Drive into:

```text
artifacts/checkpoints/shopmaibeli-sft-v3/
```

serve it with:

```bash
python models/serve.py \
  --adapter_path artifacts/checkpoints/shopmaibeli-sft-v3 \
  --port 8001
```

Then set:

```bash
DEEPSEEK_API_KEY=your-key-here
SFT_MODEL_URL=http://localhost:8001
```

in `backend/.env`, restart the app with `./stop.sh && ./start.sh`, and verify
`[generate_workflow] SFT model succeeded` in `backend.log`.

## Local Review Datasets

The lightweight review-retrieval path expects these files in `output/`:

- `output/amazon_reviews_sample.json`
- `output/full_amazon_fashion_review.json`

These dataset artifacts should be downloaded from Google Drive as described in
[docs/ARTIFACTS.md](docs/ARTIFACTS.md).

The current retrieval behavior is:

- `ProductSearch` first tries live product APIs (`dummyjson` / `fakestoreapi`)
- if `dummyjson` finds no products for some queries, it can fall back to local `amazon-local` results built from the review corpora
- `ReviewAnalyzer(mode="rag")` then enriches returned products by matching them against the local review JSON files

---

## Running Tests

```bash
# Run all non-integration tests (no network required)
pytest tests/ -v -m "not integration"

# Run integration tests (requires network)
pytest tests/ -v -m integration
```

---

## Project Structure

```
ShopMaiBeli/
├── frontend/                   # Chainlit UI (port 8000)
│   ├── app.py                  # Chat interface, command routing, NDJSON streaming
│   └── public/                 # Static assets
│
├── backend/                    # FastAPI server (port 8888)
│   ├── main.py                 # API endpoints (/health, /get_workflow, /run_workflow)
│   ├── workflow_generator.py   # LLM-based workflow generation (SFT → DeepSeek → fallback)
│   └── n8n_utils.py            # Workflow structure formatter
│
├── workflow_engine/            # DAG execution logic
│   ├── executor.py             # Parallel execution engine (asyncio.gather + retry)
│   ├── workflow.py             # JSON parser + topological sort (Kahn's algorithm)
│   ├── models.py               # NodeInput, NodeOutput, NodeData, NodeNotification
│   └── context.py              # ExecutionContext (session state + data passing)
│
├── nodes/                      # Node executor implementations
│   ├── product_search.py       # Fetches products from APIs with local amazon-local fallback
│   ├── review_analyzer.py      # Review analysis; default rag mode uses local review JSON files
│   ├── agent.py                # LLM agent node (DeepSeek via OpenAI API)
│   ├── chat_trigger.py         # Entry point — extracts user query
│   ├── convert_to_file.py      # Converts output to file (HTML/text)
│   ├── lm_deepseek.py          # DeepSeek LLM sub-node
│   ├── memory_buffer.py        # Conversation memory sub-node
│   ├── output_parser.py        # Structured output parser sub-node
│   └── tool_code.py            # Python code tool sub-node
│
├── models/                     # ML model components
│   ├── train.py                # LoRA SFT training script (Qwen2.5-3B-Instruct, PEFT/TRL)
│   ├── serve.py                # vLLM serving wrapper (OpenAI-compatible)
│   └── prompts/
│       ├── workflow_gen.txt    # Rich prompt for DeepSeek fallback workflow generation
│       └── workflow_gen_sft.txt# Lean schema-anchored prompt for SFT training/inference
│
├── data/
│   └── workflows/
│       └── train.jsonl         # SFT training examples (instruction → workflow JSON)
│
├── workflows/                  # Workflow JSON definitions
│   ├── example_shopping.json   # Full shopping workflow (fallback)
│   ├── with_reviews.json       # Shopping + review analysis workflow
│   └── NUS News ChatBot.json   # Original starter kit reference workflow
│
├── tests/                      # Test suite
│   ├── test_nodes.py           # Node unit tests
│   ├── test_workflow.py        # Workflow integration tests
│   ├── test_apis.py            # External API tests
│   └── test_generation.py      # Workflow generation/validation tests
│
├── docs/                       # Documentation
├── artifacts/                  # Local-only external artifacts (ignored by git)
├── requirements.txt            # Python dependencies
├── start.sh                    # Start all services
└── stop.sh                     # Stop all services
```

---

## System Architecture

```
User Query (Chainlit UI — port 8000)
         │
         ▼  /run_workflow POST
  FastAPI Backend (port 8888)
  └── WorkflowGenerator
      ├── SFT model (vLLM, SFT_MODEL_URL env)   ← if trained + served
      ├── DeepSeek API fallback (DEEPSEEK_API_KEY env)
      └── example_shopping.json fallback
         │
         ▼  Workflow JSON
  WorkflowExecutor (workflow_engine/)
  ├── Parse DAG from workflow JSON
  ├── Topological sort (Kahn's algorithm)
  ├── Group nodes into parallel execution levels
  └── asyncio.gather() for independent nodes (+ retry on failure)
         │
         ▼
  Node Executors (nodes/)
  ├── ChatTrigger     → pass user query downstream
  ├── Agent           → QueryAnalyzer: extract category/budget/priorities (DeepSeek sub-node)
  ├── ProductSearch   → fetch products from DummyJSON / FakeStoreAPI, then local amazon-local fallback
  ├── ReviewAnalyzer  → local review retrieval (`rag`) or simple fallback sentiment scoring
  ├── Agent           → ReportGenerator: ranked Markdown comparison table (DeepSeek sub-node)
  └── ConvertToFile   → package output as file
         │
         ▼
  Streaming NDJSON → frontend renders step-by-step progress + final report
```

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check — returns `{"status": "ok"}` |
| `/get_workflow` | POST | Generate and return workflow JSON for a query |
| `/run_workflow` | POST | Generate + execute workflow, stream NDJSON results |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Chainlit |
| Backend | FastAPI + uvicorn |
| Workflow Execution | asyncio (parallel DAG) |
| Workflow Generation | DeepSeek API / SFT model (Qwen2.5-3B LoRA) |
| SFT Training | PEFT + TRL (SFTTrainer) |
| SFT Serving | vLLM (OpenAI-compatible) |
| Product APIs | DummyJSON, FakeStoreAPI, mock, plus local amazon-local fallback |
| Local Review Retrieval | JSON review corpora + lightweight token-overlap retrieval |
| Testing | pytest + pytest-asyncio |

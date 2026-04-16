# ShopMaiBeli

ShopMaiBeli is an agentic shopping assistant that turns a user query into an
editable n8n-style workflow, executes that workflow as a DAG, and streams the
results back through a Chainlit UI.

## What The Current Code Does

- `frontend/app.py` sends chat messages to the backend and defaults normal chat
  messages to `run_workflow`
- `backend/main.py` exposes workflow generation, workflow execution, workflow
  editor, health, and session-management endpoints
- `backend/workflow_generator.py` generates workflows through this runtime chain:
  `SFT_MODEL_URL` -> `DEEPSEEK_API_KEY` -> `workflows/example_shopping.json`
- generated workflows are normalized before execution so older HTML-oriented
  outputs still fit the current Markdown-first frontend
- the backend caches a per-session workflow editor page at
  `/workflow_editor/{session_id}`
- the workflow engine preserves per-session context and serializes concurrent
  requests for the same session
- `frontend/app.py` also forwards uploaded files to the backend as base64
  payloads

## Current Runtime Flow

```text
Chainlit UI
  -> POST /get_workflow for workflow generation + editor link
  -> POST /run_workflow for NDJSON streaming execution

FastAPI backend
  -> generate_workflow(payload)
  -> cache editor HTML for the session
  -> WorkflowExecutor.from_json(...)

Workflow generation fallback chain
  -> SFT model via vLLM if SFT_MODEL_URL is set
  -> DeepSeek via OpenAI-compatible API if DEEPSEEK_API_KEY is set
  -> workflows/example_shopping.json otherwise
```

## Repo Layout

```text
ShopMaiBeli/
├── backend/
│   ├── main.py
│   ├── n8n_utils.py
│   └── workflow_generator.py
├── frontend/
│   ├── app.py
│   ├── chainlit.md
│   └── public/
├── models/
│   ├── prompts/
│   ├── serve.py
│   └── train.py
├── nodes/
│   ├── agent.py
│   ├── chat_trigger.py
│   ├── convert_to_file.py
│   ├── lm_deepseek.py
│   ├── memory_buffer.py
│   ├── output_parser.py
│   ├── product_search.py
│   ├── review_analyzer.py
│   └── tool_code.py
├── output/
├── scripts/
├── tests/
├── workflow_engine/
├── workflows/
├── DEMO_INSTRUCTIONS.md
├── requirements.txt
├── start.sh
└── stop.sh
```

## Setup

### Prerequisites

- Python 3.11+ is a safe target for the checked-in code and tests
- a virtual environment is recommended

### Install

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
```

If you want to run the async pytest suite locally, install the test
plugin too:

```bash
python -m pip install pytest-asyncio
```

If you want to train or serve the SFT model, install those extras separately:

```bash
python -m pip install torch transformers peft trl datasets accelerate bitsandbytes vllm
```

## Environment Variables

The backend loads `backend/.env` first, then the project-root `.env`.

### DeepSeek-only generation

```bash
cat > backend/.env <<'EOF'
DEEPSEEK_API_KEY=your_key_here
EOF
```

### SFT-first generation

```bash
cat > backend/.env <<'EOF'
SFT_MODEL_URL=http://localhost:8001
DEEPSEEK_API_KEY=your_key_here
EOF
```

`SFT_MODEL_URL` should point to an OpenAI-compatible vLLM server that exposes
the LoRA adapter as `shopmaibeli-sft`.

## Run The App

From the project root:

```bash
source .venv/bin/activate
./start.sh
```

This starts:

- backend on `http://localhost:8888`
- frontend on `http://localhost:8000`

Logs go to:

- `backend.log`
- `frontend.log`

Stop both services with:

```bash
./stop.sh
```

## Backend Endpoints

| Endpoint | Method | Current behavior |
|---|---|---|
| `/health` | `GET` | Returns `{"status":"ok"}` |
| `/get_workflow` | `POST` | Generates a workflow and returns a message payload with an editor link |
| `/workflow_editor/{session_id}` | `GET` | Serves the cached HTML editor for that session |
| `/run_workflow` | `POST` | Executes a provided workflow or a generated workflow and streams NDJSON |
| `/sessions` | `GET` | Lists active session metadata |
| `/sessions/{session_id}` | `DELETE` | Evicts one session from the store |

## Frontend Behavior

- Chainlit registers two commands: `get_workflow` and `run_workflow`
- ordinary chat messages default to `run_workflow`
- the only chat setting is `Base URL`, defaulting to
  `http://localhost:8888`
- streamed backend events are rendered as Chainlit messages or steps
- uploaded files are read locally, base64-encoded, and forwarded in the request

## Data And Retrieval

- `nodes/product_search.py` can use `fakestoreapi`, `dummyjson`, or `mock`
- DummyJSON is preferred when FakeStoreAPI fails and there is a local query to
  map
- if network product search fails, the code can still fall back to local mock
  data
- `nodes/review_analyzer.py` defaults to `rag` mode and looks for:
  `output/full_amazon_fashion_review.json` and
  `output/amazon_reviews_sample.json`
- if no review corpus is available or no match is found, review analysis falls
  back to a simple rating-based summary

## SFT Training And Serving

Train:

```bash
python models/train.py \
  --data_dir data/workflows/train.jsonl \
  --output_dir models/checkpoints/shopmaibeli-sft \
  --epochs 3 \
  --strict_validation \
  --seed 42
```

Serve with the helper script:

```bash
python models/serve.py \
  --adapter_path models/checkpoints/shopmaibeli-sft \
  --port 8001
```

Or serve directly with vLLM:

```bash
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-3B-Instruct \
  --enable-lora \
  --lora-modules shopmaibeli-sft=models/checkpoints/shopmaibeli-sft \
  --max-lora-rank 64 \
  --port 8001 \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.9 \
  --dtype bfloat16 \
  --trust-remote-code
```

When the SFT path is exercised, raw model responses are also written under
`artifacts/sft_debug/`.

## Tests

The current test tree collects 61 tests. Ten are marked `integration`, so the
local non-integration command currently targets 51 tests.

Non-integration:

```bash
python -m pytest tests -m "not integration"
```

Integration:

```bash
python -m pytest tests -m integration
```

Notes:

- integration tests require network access and, for backend API checks, a
  running local server
- the async tests require `pytest-asyncio`, which is not currently installed by
  `requirements.txt` alone

## Related Docs

- [DEMO_INSTRUCTIONS.md](DEMO_INSTRUCTIONS.md)
- [docs/ARTIFACTS.md](docs/ARTIFACTS.md)

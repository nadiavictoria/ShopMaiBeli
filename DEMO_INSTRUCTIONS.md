# Demo Instructions

This guide matches the current code paths in `frontend/app.py`,
`backend/main.py`, and `backend/workflow_generator.py`.

There are two practical demo modes:

- `DeepSeek or fallback demo`: no local SFT server required
- `SFT demo`: workflow generation goes to a served LoRA adapter first, with
  DeepSeek still available as the backend fallback path

## Local App Setup

### 1. Create The Environment

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
```

If you plan to run tests during the demo setup, also install:

```bash
python -m pip install pytest-asyncio
```

### 2. Configure `backend/.env`

DeepSeek-backed generation:

```bash
cat > backend/.env <<'EOF'
DEEPSEEK_API_KEY=your_key_here
EOF
```

SFT-first generation with DeepSeek fallback:

```bash
cat > backend/.env <<'EOF'
SFT_MODEL_URL=http://localhost:8001
DEEPSEEK_API_KEY=your_key_here
EOF
```

If neither variable is set, the backend still runs and falls back to
`workflows/example_shopping.json`.

### 3. Start The Services

```bash
source .venv/bin/activate
./start.sh
```

This launches:

- backend on `http://localhost:8888`
- frontend on `http://localhost:8000`

Logs:

- `backend.log`
- `frontend.log`

### 4. Sanity Check The Backend

```bash
curl http://localhost:8888/health
```

Expected:

```json
{"status":"ok"}
```

### 5. Open The UI

Visit:

```text
http://localhost:8000
```

The current frontend behavior is:

- normal chat messages default to `run_workflow`
- the command palette includes `get_workflow` and `run_workflow`
- `Base URL` defaults to `http://localhost:8888`
- file attachments are forwarded to the backend

### 6. Stop The App

```bash
./stop.sh
```

## Demo Flow To Show Teammates

### Option A: Show The Workflow Editor First

1. In Chainlit, choose the `get_workflow` command.
2. Ask for something like `find wireless earbuds under $80`.
3. Open the returned editor link.

What happens in the current code:

- `POST /get_workflow` generates a workflow from the latest chat message
- the backend caches the generated workflow HTML per session
- the response is a message with an `Open Editor` link

### Option B: Show Full Execution

1. Send a normal chat message in the UI.
2. The frontend defaults that to `run_workflow`.
3. Watch the streamed steps arrive in the chat.

What happens in the current code:

- `POST /run_workflow` either uses a provided workflow from the payload or
  generates one on the fly
- the backend sends an initial `Workflow Used` message containing the editor
  link
- execution results stream back as NDJSON and render as Chainlit steps/messages

## Current Generation Chain

`backend/workflow_generator.py` now uses this order:

1. `SFT_MODEL_URL`
2. `DEEPSEEK_API_KEY`
3. `workflows/example_shopping.json`

Important details:

- generated workflows are validated before use
- generated workflows are normalized to the current Markdown-first report format
- old `dummy_store` and `fakestore` source names are normalized to
  `dummyjson` and `fakestoreapi`
- raw SFT outputs are written to `artifacts/sft_debug/`

## Good Demo Queries

- `find me wireless earbuds under $80`
- `show me a women's black handbag for work under $120`
- `recommend a mechanical keyboard for coding under $100`
- `best webcam for online meetings under $70`

These work well because the current product search implementation has explicit
DummyJSON query/category handling for electronics and accessories.

## SFT Demo Setup

### 1. Install Training And Serving Extras On The GPU Machine

```bash
python -m pip install torch transformers peft trl datasets accelerate bitsandbytes vllm
```

### 2. Train The Adapter

```bash
python models/train.py \
  --data_dir data/workflows/train.jsonl \
  --output_dir models/checkpoints/shopmaibeli-sft \
  --epochs 3 \
  --strict_validation \
  --seed 42
```

Use the curated training file `data/workflows/train.jsonl`, not the whole
directory.

### 3. Serve The Adapter

Using the helper:

```bash
python models/serve.py \
  --adapter_path models/checkpoints/shopmaibeli-sft \
  --port 8001
```

Or directly via vLLM:

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

### 4. Verify The SFT Server

From a shell that can reach the GPU host:

```bash
curl http://<gpu-host>:8001/v1/models
```

You should see the registered adapter name `shopmaibeli-sft`.

### 5. Tunnel To Your Laptop If Needed

Example:

```bash
ssh -L 8001:<gpu-host>:8001 your_soc_unix_id@xlogin.comp.nus.edu.sg
```

Then local verification:

```bash
curl http://localhost:8001/v1/models
```

### 6. Restart The Local App

```bash
./stop.sh
./start.sh
```

### 7. Confirm SFT Is Being Used

After sending a query, inspect:

```bash
tail -n 100 backend.log
```

Look for one of these current log lines:

```text
[generate_workflow] SFT model succeeded
[generate_workflow] DeepSeek fallback succeeded
[generate_workflow] Using hardcoded fallback workflow
```

If SFT emits malformed output, the raw response is also captured under
`artifacts/sft_debug/latest_raw_response.txt`.

## What The Current App Actually Demonstrates

### Workflow Generation

- SFT-first generation via OpenAI-compatible vLLM
- DeepSeek fallback generation
- hardcoded example workflow as the last safety net
- validation and normalization before execution

### Workflow Execution

- DAG parsing and execution through `WorkflowExecutor`
- streamed NDJSON updates
- per-session state persistence
- same-session request serialization
- session observability via `/sessions`

### Nodes

- `ChatTrigger`
- `Agent`
- `ProductSearch`
- `ReviewAnalyzer`
- `ConvertToFile`
- `lmChatDeepSeek`
- `memoryBufferWindow`
- `outputParserStructured`
- `toolCode`

### Search And Reviews

- product search via `fakestoreapi`, `dummyjson`, or mock fallback
- review analysis via local JSON review corpora in `output/`
- simple rating-based fallback when no review corpus match is found

## Test Commands

Non-integration:

```bash
python -m pytest tests -m "not integration"
```

Integration:

```bash
python -m pytest tests -m integration
```

Current caveat:

- the repo collects async tests, but `requirements.txt` does not currently
  install `pytest-asyncio`, so install that plugin first if you want the suite
  to run cleanly

# Demo Instructions — ShopMaiBeli

This guide covers two demo modes:

- `Fallback demo`: fastest local setup, uses fallback workflows and may use mock data
- `SFT demo`: uses the fine-tuned workflow generator served from a GPU machine, with DeepSeek still used inside workflow agent nodes

---

## Quick Start

### 1. Install Dependencies

From the project root:

```bash
source venv/bin/activate
python -m pip install -r requirements.txt
```

### 2. Configure Environment

For local workflow execution with DeepSeek-backed agent nodes:

```bash
cat > backend/.env <<'EOF'
DEEPSEEK_API_KEY=your_key_here
EOF
```

If you are also using the SFT model through an SSH tunnel on your Mac:

```bash
cat > backend/.env <<'EOF'
SFT_MODEL_URL=http://localhost:8001
DEEPSEEK_API_KEY=your_key_here
EOF
```

### 3. Start Both Services

```bash
./start.sh
```

This launches:

- `Backend` on `http://localhost:8888`
- `Frontend` on `http://localhost:8000`

Logs are written to `backend.log` and `frontend.log`.

### 4. Verify the Backend

```bash
curl http://localhost:8888/health
```

Expected:

```json
{"status":"ok"}
```

### 5. Open the Frontend

Visit:

```text
http://localhost:8000
```

You can now type directly into the chat box. Plain messages default to `run_workflow`.

### 6. Stop the App

```bash
./stop.sh
```

---

## Demo Modes

### Fallback Demo

This is the simplest path when you only want to show the app running locally.

What it demonstrates:

- frontend/backend integration
- workflow execution
- streaming progress updates
- retry/fallback behavior

What it may use:

- generated workflows from DeepSeek, if configured
- fallback workflow JSON if generation is unavailable
- live product APIs where possible
- mock fallback if external product search fails

Good test queries:

- `find me wireless earbuds under $80`
- `i want to buy a samsung galaxy watch`
- `show me laptops with good reviews`

### SFT Demo

This uses your fine-tuned workflow generator for the `/get_workflow` and `/run_workflow` planning step.

Important:

- the SFT model replaces workflow generation
- DeepSeek is still required for `QueryAnalyzer` and `ReportGenerator` nodes in the current workflow design

So the current runtime split is:

- `SFT model`: generates the workflow JSON
- `DeepSeek`: powers agent reasoning nodes inside that workflow

---

## SFT Setup

### 1. Train the SFT Model on a GPU Machine

On the GPU environment:

```bash
python models/train.py \
  --data_dir data/workflows \
  --output_dir models/checkpoints/shopmaibeli-sft \
  --epochs 3
```

This saves the LoRA adapter under:

```text
models/checkpoints/shopmaibeli-sft
```

### 2. Serve the Adapter with vLLM

On a GPU node:

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

### 3. Verify the Model Server

From another shell on the same network:

```bash
curl http://<gpu-node-hostname>:8001/v1/models
```

You should see both the base model and `shopmaibeli-sft`.

### 4. Tunnel the Model to Your Mac

If the model is running on a cluster GPU node and your app is running locally:

```bash
ssh -L 8001:<gpu-node-hostname>:8001 your_soc_unix_id@xlogin.comp.nus.edu.sg
```

Leave that SSH session open. Then verify from your Mac:

```bash
curl http://localhost:8001/v1/models
```

### 5. Point the Backend to SFT

On your local machine:

```bash
cat > backend/.env <<'EOF'
SFT_MODEL_URL=http://localhost:8001
DEEPSEEK_API_KEY=your_key_here
EOF
```

Restart the app:

```bash
./stop.sh
./start.sh
```

### 6. Confirm the App Is Using SFT

After sending a chat message, inspect the backend log:

```bash
tail -n 100 backend.log
```

You want to see:

```text
[generate_workflow] SFT model succeeded
```

---

## What Is Implemented

### Workflow Execution

- parallel execution with `asyncio.gather()`
- retry with exponential backoff
- graceful fallback when product search sources fail

### Nodes

- `ChatTrigger`
- `QueryAnalyzer` via agent node
- `ProductSearch`
- `ReviewAnalyzer`
- `ReportGenerator`
- `ConvertToFile`

### Workflow Generation

- SFT model via `SFT_MODEL_URL`
- DeepSeek fallback via `DEEPSEEK_API_KEY`
- hardcoded fallback workflow as final safety net

### Tests

Run non-integration tests with:

```bash
python -m pytest tests/ -v -m "not integration"
```

Current expected result:

- `40 passed`
- `10 deselected`

---

## Known Limitations

- The current workflow execution still uses DeepSeek for agent nodes even when SFT is enabled.
- `ReviewAnalyzer` RAG mode is still a placeholder and falls back to simple rating-based analysis.
- The trained SFT data may still prefer HTML-style report workflows, so the backend currently normalizes report prompts/output back toward Markdown for frontend reliability.
- Product search uses external demo/sample APIs (`dummyjson`, `fakestoreapi`) rather than production commerce APIs.

---

## Troubleshooting

### `async def functions are not natively supported`

You are probably running the wrong pytest binary. Use:

```bash
python -m pytest tests/ -v -m "not integration"
```

### `DeepSeek API key not found`

Your workflow contains agent nodes using DeepSeek, but `backend/.env` does not contain:

```text
DEEPSEEK_API_KEY=...
```

### `SFT model failed`

Check:

```bash
curl http://localhost:8001/v1/models
tail -n 100 backend.log
```

If `localhost:8001` is tunneled from a cluster node, make sure:

- the GPU serving process is still running
- the SSH tunnel terminal is still open

### Product search falls back to mock

Check `backend.log` for:

- invalid product API URL construction
- DummyJSON/FakeStore failures
- fallback messages like `using mock data`

### Ports already in use

```bash
lsof -i :8000
lsof -i :8888
./stop.sh
```

---

## Demo Checklist

For a live SFT demo, keep these running:

1. GPU-node model server on port `8001`
2. SSH tunnel from your Mac to the GPU node
3. local `./start.sh` app session

Before presenting:

```bash
curl http://localhost:8001/v1/models
curl http://localhost:8888/health
tail -n 50 backend.log
```

You want to confirm:

- the SFT model endpoint is reachable
- the backend is healthy
- the backend logs show `SFT model succeeded`

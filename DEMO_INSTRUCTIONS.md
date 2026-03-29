# Demo Instructions — ShopMaiBeli Execution Engine

## Quick Start (2 minutes)

### 1. Install Dependencies

```bash
# From the project root — activate your virtual environment first
source ./my-venv/bin/activate

# Install all requirements
pip install -r requirements.txt
```

### 2. Start Both Services

```bash
# Always run from the project root
./start.sh
```

This launches:
- **Backend** on http://localhost:8888 (FastAPI + Workflow Executor)
- **Frontend** on http://localhost:8000 (Chainlit UI)

Logs are written to `backend.log` and `frontend.log` in the project root.

### 3. Open the Frontend

Visit **http://localhost:8000** in your browser. You should see the Chainlit chat interface.

### 4. Try the Demo

Send a message like:
```
find earbuds
```

**What happens step by step:**
1. Frontend sends query to backend `/get_workflow` → displays workflow structure
2. Frontend sends query to backend `/run_workflow` → streams execution
3. Backend loads `workflows/example_shopping.json`
4. Execution engine runs the workflow:
   - **Trigger** node extracts the query
   - **ProductSearch** node searches using mock data
   - Each step streams back to the chat in real time
5. Final result shows the found products

**Try different queries** (all use offline mock data):
- "headphones"
- "smart watch"
- "usb charger"
- "laptop bag"

### 5. Stop the Application

```bash
./stop.sh
```

---

## What's Being Demonstrated

### ✅ Execution Engine (Points 1 & 2)

**Parallel execution** — nodes with no mutual dependencies run concurrently via `asyncio.gather()`:
```
Trigger → [Search A, Search B] → ReviewAnalyzer
               ↑ these two run in parallel
```

**Retry with exponential backoff** — each node retries up to 3 times on failure (delays: 1s, 2s, 4s)

**ProductSearch node** (`nodes/product_search.py`):
- `source: "mock"` — 5 hardcoded products, no network needed
- `source: "fakestoreapi"` — live data from fakestoreapi.com
- `source: "dummyjson"` — live data from dummyjson.com

**ReviewAnalyzer node** (`nodes/review_analyzer.py`):
- Adds `review_sentiment`, `review_summary`, `review_confidence` to each product
- Simple mode: derives sentiment from product rating (≥4.0 → positive, 3.0-4.0 → neutral, <3.0 → negative)
- RAG mode: placeholder, falls back to simple (FAISS integration pending)

### ✅ Test Suite

39 tests, all passing. No network required for the core tests:

```bash
pytest tests/ -v -m "not integration"
```

Test files:
- `tests/test_nodes.py` — 15 unit tests (ProductSearch + ReviewAnalyzer)
- `tests/test_workflow.py` — 13 workflow-level tests (parallel execution, session isolation)
- `tests/test_generation.py` — 11 validation tests (workflow JSON structure)
- `tests/test_apis.py` — 7 integration tests (requires network, run with `-m integration`)

### ✅ Example Workflows

Two ready-to-use workflow JSON files in `workflows/`:

| File | Pipeline |
|---|---|
| `example_shopping.json` | Trigger → ProductSearch (mock) |
| `with_reviews.json` | Trigger → ProductSearch → ReviewAnalyzer |

### 🚧 Workflow Generation (Point 3 — Upcoming)

Currently `generate_workflow()` in `backend/main.py` returns the hardcoded `example_shopping.json`.

Next step: replace this with an LLM call (Claude API or fine-tuned Qwen SFT model) that generates workflow JSON dynamically from the user's query.

---

## Running Services Manually (for debugging)

If `./start.sh` doesn't work, start each service manually from the **project root**:

**Terminal 1 — Backend:**
```bash
source ./my-venv/bin/activate
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8888
```

**Terminal 2 — Frontend:**
```bash
source ./my-venv/bin/activate
chainlit run frontend/app.py --port 8000
```

**Verify backend is running:**
```bash
curl http://localhost:8888/health
# Expected: {"status":"ok"}
```

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'workflow_engine'`**
→ You're not running from the project root. Always use `./start.sh` or `python -m uvicorn` from the root.

**`ModuleNotFoundError: No module named 'openai'`**
→ `openai` is optional (only needed for DeepSeek LLM nodes). Install it with `pip install openai` or ignore — tests will still pass without it.

**Tests failing with `async def functions are not natively supported`**
→ Your `pytest` is from the wrong Python environment. Run with the venv pytest:
```bash
./my-venv/bin/pytest tests/ -v -m "not integration"
```

**`Streaming request failed: All connection attempts failed`**
→ Backend isn't running. Check `backend.log` and verify `curl http://localhost:8888/health` returns OK.

**Port already in use:**
```bash
lsof -i :8888   # find process using port
lsof -i :8000
./stop.sh       # or just stop existing services
```

---

## Architecture Overview

```
User Message (http://localhost:8000)
       │
       ▼ HTTP POST /get_workflow + /run_workflow
FastAPI Backend (http://localhost:8888)
  backend/main.py
       │
       ▼ loads JSON
workflows/example_shopping.json
       │
       ▼ parses DAG
workflow_engine/
  ├── workflow.py    → topological sort
  ├── executor.py    → parallel levels + asyncio.gather()
  └── context.py     → session state
       │
       ▼ delegates to
nodes/
  ├── chat_trigger.py   → extracts query
  ├── product_search.py → fetches products (mock/live)
  └── review_analyzer.py → adds sentiment
       │
       ▼ streams NodeNotification objects
Frontend renders steps + final message
```

---

**Reference:** See `docs/implementation-plan.md` for the full technical implementation log.

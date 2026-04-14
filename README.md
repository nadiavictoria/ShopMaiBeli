# ShopMaiBeli — Agentic Shopping Assistant

ShopMaiBeli is an **agentic AI system** that transforms natural language shopping requests into executable workflow graphs, runs them against live product APIs, and returns ranked comparison results.

Instead of returning a simple list of items, the system:
- generates a **workflow graph (DAG)** of actions,
- executes it with **parallel processing and failure recovery**, and
- returns **structured product results with review analysis**.

---

## Current Status

| Component | Status | Notes |
|---|---|---|
| Project Migration | ✅ Complete | Flat structure: `backend/`, `frontend/`, `workflow_engine/`, `nodes/` |
| Execution Engine | ✅ Complete | Parallel execution, retry logic, streaming NDJSON |
| ProductSearch Node | ✅ Complete | Mock, FakeStoreAPI, DummyJSON backends |
| ReviewAnalyzer Node | ✅ Complete | Simple sentiment mode, RAG placeholder |
| Test Suite | ✅ Complete | 39 tests passing |
| Example Workflows | ✅ Complete | `example_shopping.json`, `with_reviews.json` |
| Frontend (Chainlit) | ✅ Running | Chat UI with streaming step display |
| Backend (FastAPI) | ✅ Running | `/health`, `/get_workflow`, `/run_workflow` |
| Workflow Generation | 🚧 Placeholder | Returns hardcoded `example_shopping.json` — LLM integration pending (Point 3) |
| SFT Model | 🚧 Pending | Qwen-2.5 3B LoRA — not yet integrated |

---

## Getting Started

### Prerequisites
- Python 3.13+
- Virtual environment (recommended)

### 1. Clone and Set Up

```bash
git clone <repo-url>
cd ShopMaiBeli

# Create and activate virtual environment
python -m venv my-venv
source my-venv/bin/activate   # Windows: my-venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Start the Application

```bash
# From the project root
./start.sh
```

This launches:
- **Backend** on http://localhost:8888 (FastAPI)
- **Frontend** on http://localhost:8000 (Chainlit)

### 3. Open the Chat Interface

Visit **http://localhost:8000** in your browser.

Send a message like:
```
find earbuds
```

The system will:
1. Load the example shopping workflow
2. Run ProductSearch using mock data
3. Stream results back step by step

### 4. Stop the Application

```bash
./stop.sh
```

---

## Running Tests

```bash
# Activate your virtual environment first
source my-venv/bin/activate

# Run all non-integration tests (no network required)
pytest tests/ -v -m "not integration"

# Run integration tests (requires network)
pytest tests/ -v -m integration
```

Expected output: **39 tests passing** in ~2 seconds.

---

## Project Structure

```
ShopMaiBeli/
├── frontend/                   # Chainlit UI (port 8000)
│   ├── app.py                  # Main Chainlit application
│   ├── chainlit.md             # Welcome page
│   └── public/                 # Static assets
│
├── backend/                    # FastAPI server (port 8888)
│   ├── main.py                 # API endpoints
│   └── n8n_utils.py            # Workflow structure formatter
│
├── workflow_engine/            # DAG execution logic
│   ├── __init__.py             # Exports WorkflowExecutor
│   ├── executor.py             # Parallel execution engine
│   ├── workflow.py             # JSON parser + topological sort
│   ├── models.py               # NodeInput, NodeOutput, etc.
│   └── context.py              # ExecutionContext (session state)
│
├── nodes/                      # Node executor implementations
│   ├── __init__.py             # Registry + get_executor_class()
│   ├── base.py                 # BaseNodeExecutor (abstract)
│   ├── product_search.py       # ProductSearch node ✅ NEW
│   ├── review_analyzer.py      # ReviewAnalyzer node ✅ NEW
│   ├── chat_trigger.py         # Entry point node
│   ├── agent.py                # LLM agent node
│   ├── convert_to_file.py      # HTML output node
│   ├── lm_deepseek.py          # DeepSeek LLM sub-node (optional)
│   ├── memory_buffer.py        # Memory sub-node
│   ├── output_parser.py        # Output parser sub-node
│   └── tool_code.py            # Python code tool sub-node
│
├── workflows/                  # Workflow JSON definitions
│   ├── example_shopping.json   # Trigger → ProductSearch
│   ├── with_reviews.json       # Trigger → ProductSearch → ReviewAnalyzer
│   └── NUS News ChatBot.json   # Original starter kit workflow
│
├── tests/                      # Test suite (39 tests)
│   ├── conftest.py             # Pytest async configuration
│   ├── test_nodes.py           # Node unit tests (15 tests)
│   ├── test_workflow.py        # Workflow integration tests (13 tests)
│   ├── test_apis.py            # External API tests (7 tests)
│   └── test_generation.py      # Workflow validation tests (11 tests)
│
├── docs/                       # Documentation
│   ├── architecture.md         # System architecture
│   ├── implementation-plan.md  # Implementation progress
│   ├── nodes.md                # Node specifications
│   ├── testing.md              # Testing strategy
│   ├── requirements.md         # Workflow generation specs
│   └── claude-code-guide.md    # Development guide
│
├── pytest.ini                  # Pytest configuration
├── requirements.txt            # Python dependencies
├── start.sh                    # Start all services from project root
├── stop.sh                     # Stop all services
└── DEMO_INSTRUCTIONS.md        # Step-by-step demo guide for teammates
```

---

## System Architecture

```
User Query (Chainlit UI — port 8000)
         │
         ▼
  FastAPI Backend (port 8888)
  ├── POST /get_workflow  → loads workflow JSON + formats structure
  └── POST /run_workflow  → executes + streams NDJSON results
         │
         ▼
  WorkflowExecutor (workflow_engine/)
  ├── Parses DAG from workflow JSON
  ├── Topological sort (Kahn's algorithm)
  ├── Groups nodes into parallel execution levels
  └── asyncio.gather() for concurrent nodes
         │
         ▼
  Node Executors (nodes/)
  ├── ChatTrigger     → extracts user query from chat history
  ├── ProductSearch   → fetches products (mock / fakestoreapi / dummyjson)
  └── ReviewAnalyzer  → adds sentiment scores to products
         │
         ▼
  Streaming NDJSON → frontend renders step-by-step progress
```

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check — returns `{"status": "ok"}` |
| `/get_workflow` | POST | Returns workflow structure as markdown text |
| `/run_workflow` | POST | Executes workflow, streams NDJSON results |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Chainlit |
| Backend | FastAPI + uvicorn |
| Workflow Execution | asyncio (parallel DAG) |
| Product APIs | FakeStoreAPI, DummyJSON (+ mock) |
| Node LLM | DeepSeek API (optional) |
| Testing | pytest + pytest-asyncio |

---

## Next Steps (Point 3: Workflow Generation)

The `generate_workflow()` function in `backend/main.py` currently returns a hardcoded `example_shopping.json`. The next implementation step replaces this with a model call that generates workflow JSON dynamically from a user query. See `docs/implementation-plan.md` for the full roadmap.

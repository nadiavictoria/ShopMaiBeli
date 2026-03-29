# Architecture

## Implementation Status (as of 2026-03-29)

| Component | Status |
|---|---|
| Project structure migration | ✅ Complete |
| `workflow_engine/` — parallel executor, retry logic | ✅ Complete |
| `nodes/product_search.py` | ✅ Complete |
| `nodes/review_analyzer.py` | ✅ Complete (simple mode; RAG placeholder) |
| `backend/main.py` — FastAPI endpoints | ✅ Running |
| `frontend/app.py` — Chainlit UI | ✅ Running |
| `start.sh` / `stop.sh` | ✅ Working (must run from project root) |
| Test suite — 39 tests | ✅ All passing |
| Workflow generation (LLM → JSON) | 🚧 Placeholder — returns hardcoded `example_shopping.json` |
| SFT model integration (Qwen) | 🚧 Pending |
| FAISS review index — RAG mode | 🚧 Pending |

---

## Project Structure

```
shopmaibeli/
├── frontend/                          # Chainlit UI
│   ├── app.py                         # Main Chainlit application
│   ├── chainlit.md                    # Welcome page
│   ├── .chainlit/config.toml          # Chainlit config
│   └── public/
│       └── elements/
│           └── HtmlPreview.jsx        # Custom sidebar HTML preview component
│
├── backend/                           # FastAPI server
│   ├── main.py                        # API entry point (/health, /get_workflow, /run_workflow)
│   ├── n8n_utils.py                   # n8n visualization HTML generator
│   └── .env                           # API keys (DEEPSEEK_API_KEY)
│
├── workflow_engine/                   # DAG execution logic
│   ├── __init__.py                    # Package exports (WorkflowExecutor)
│   ├── models.py                      # Data models (Node, NodeData, NodeInput, NodeOutput, etc.)
│   ├── workflow.py                    # Workflow parser (JSON → connection graph, topological sort)
│   ├── context.py                     # ExecutionContext (session state, node outputs, memory)
│   └── executor.py                    # WorkflowExecutor (main execution loop)
│
├── nodes/                             # Node executor implementations
│   ├── __init__.py                    # NODE_EXECUTOR_REGISTRY + get_executor_class()
│   ├── base.py                        # BaseNodeExecutor (abstract base class)
│   ├── chat_trigger.py                # ChatTrigger — entry point
│   ├── agent.py                       # AgentExecutor — LLM agent with tool-calling loop
│   ├── product_search.py              # ProductSearch — calls product APIs [NEW]
│   ├── review_analyzer.py             # ReviewAnalyzer — RAG over reviews [NEW]
│   ├── convert_to_file.py             # ConvertToFile — HTML output
│   ├── lm_deepseek.py                 # DeepSeek LLM sub-node
│   ├── memory_buffer.py               # Memory sub-node
│   ├── output_parser.py               # Output parser sub-node
│   └── tool_code.py                   # Python code tool sub-node
│
├── models/                            # SFT model + inference
│   ├── train.py                       # LoRA SFT training script
│   ├── serve.py                       # vLLM serving config
│   └── prompts/                       # System prompts for workflow generation
│       └── workflow_gen.txt
│
├── data/                              # Training + RAG data
│   ├── workflows/                     # SFT training examples (query → JSON pairs)
│   ├── products/                      # Product catalog / mock data
│   └── reviews/                       # Review dataset for FAISS index
│
├── docs/                              # Documentation
│   ├── architecture.md                # This file
│   ├── requirements.md                # Workflow generation specs
│   ├── prompt-improver.md             # Prompt engineering guide
│   ├── implementation-plan.md         # Execution engine implementation
│   ├── nodes.md                       # Node type specifications
│   ├── testing.md                     # Testing strategy
│   ├── security.md                    # Security considerations
│   └── claude-code-guide.md           # Guide for using Claude Code on this project
│
├── workflows/                         # Workflow JSON definitions
│   └── example_shopping.json          # Example workflow for testing
│
├── n8n.html                           # Read-only workflow visualization
├── n8n_editable.html                  # Editable workflow visualization (bonus)
├── start.sh                           # Start frontend + backend
├── stop.sh                            # Stop services
├── requirements.txt                   # Python dependencies
└── README.md
```

## Migration Map (Starter Kit → ShopMaiBeli)

| Starter Kit Path | New Path | Notes |
|---|---|---|
| `chatbot/app.py` | `frontend/app.py` | Update backend URL default if needed |
| `chatbot/chainlit.md` | `frontend/chainlit.md` | Update welcome text |
| `chatbot/.chainlit/config.toml` | `frontend/.chainlit/config.toml` | Update app name |
| `chatbot/public/elements/HtmlPreview.jsx` | `frontend/public/elements/HtmlPreview.jsx` | No changes |
| `server/main.py` | `backend/main.py` | Update imports from `workflow` → `workflow_engine`, modify `generate_workflow()` |
| `server/n8n_utils.py` | `backend/n8n_utils.py` | No changes |
| `server/.env` | `backend/.env` | No changes |
| `server/NUS News ChatBot.json` | `workflows/example_shopping.json` | Replace with shopping workflow |
| `server/workflow/__init__.py` | `workflow_engine/__init__.py` | Update import paths |
| `server/workflow/models.py` | `workflow_engine/models.py` | No changes |
| `server/workflow/workflow.py` | `workflow_engine/workflow.py` | No changes |
| `server/workflow/context.py` | `workflow_engine/context.py` | No changes |
| `server/workflow/executor.py` | `workflow_engine/executor.py` | Update node import, add parallel execution |
| `server/workflow/nodes/*` | `nodes/*` | Update imports from `..models` → `workflow_engine.models` |
| — | `nodes/product_search.py` | New file |
| — | `nodes/review_analyzer.py` | New file |
| `n8n.html` | `n8n.html` | No changes |
| `n8n_editable.html` | `n8n_editable.html` | No changes |
| `start.sh` | `start.sh` | Rewritten: stays at project root, uses `python -m uvicorn backend.main:app` |
| `stop.sh` | `stop.sh` | No changes |
| `environment.yml` | `requirements.txt` | Convert conda env to pip requirements |

### Import changes after migration

When moving `nodes/` out of `workflow_engine/`, internal imports change:

```python
# BEFORE (starter kit): nodes are inside server/workflow/nodes/
from ..models import NodeInput, NodeOutput  # relative import
from ..context import ExecutionContext

# AFTER (new structure): nodes/ is a sibling of workflow_engine/
from workflow_engine.models import NodeInput, NodeOutput  # absolute import
from workflow_engine.context import ExecutionContext
```

Similarly in `workflow_engine/executor.py`:
```python
# BEFORE
from .nodes import get_executor_class

# AFTER
from nodes import get_executor_class
```

And in `backend/main.py`:
```python
# BEFORE
from workflow import WorkflowExecutor

# AFTER
from workflow_engine import WorkflowExecutor
```

## System Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                       ShopMaiBeli System                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │           frontend/ — Chainlit (Port 8000)                 │   │
│  │  Chat UI · Workflow Preview · HTML Report · Streaming      │   │
│  └─────────────────────────┬─────────────────────────────────┘   │
│                             │ HTTP (JSON / NDJSON)                 │
│  ┌─────────────────────────▼─────────────────────────────────┐   │
│  │           backend/ — FastAPI (Port 8888)                    │   │
│  │  /get_workflow    → calls workflow generator                │   │
│  │  /run_workflow    → streams execution via NDJSON            │   │
│  └─────────┬───────────────────────────────────┬─────────────┘   │
│            │                                   │                  │
│  ┌─────────▼──────────┐          ┌─────────────▼─────────────┐   │
│  │  models/            │          │  workflow_engine/          │   │
│  │  SFT Model (Qwen)  │          │  Workflow parser           │   │
│  │  served via vLLM    │          │  Topological sort          │   │
│  │                     │          │  Parallel executor         │   │
│  └────────────────────┘          └──────────┬────────────────┘   │
│                                              │                    │
│                                   ┌──────────▼────────────────┐  │
│                                   │  nodes/                    │  │
│                                   │  ChatTrigger · Agent       │  │
│                                   │  ProductSearch · Review    │  │
│                                   │  ConvertToFile · LLM       │  │
│                                   └───────────────────────────┘  │
│                                                                   │
│  External: DeepSeek API · FakeStoreAPI · DummyJSON · FAISS        │
└──────────────────────────────────────────────────────────────────┘
```

## Data Flow

1. User types a shopping query in the Chainlit chat UI
2. Frontend sends POST to `backend/main.py` `/get_workflow` endpoint
3. Backend calls the SFT model (or DeepSeek API with prompting) to generate Workflow JSON
4. Backend returns the JSON + n8n visualization HTML to frontend
5. User clicks "run_workflow" to execute
6. Frontend sends POST to `/run_workflow` with session_id and chat_history
7. Backend creates a `WorkflowExecutor`, calls `execute()` which:
   - Parses the JSON via `workflow_engine/workflow.py`
   - Topological sorts the nodes
   - Executes each node (parallel where possible) via executors in `nodes/`
   - Yields `NodeNotification` after each node completes
8. Backend streams notifications as NDJSON lines
9. Frontend renders each notification as a Chainlit Step (progress) or Message (final result)
10. Final node output is an HTML report displayed in the sidebar via HtmlPreview component

## Ports

| Service | Port | URL |
|---|---|---|
| Chainlit Frontend | 8000 | http://localhost:8000 |
| FastAPI Backend | 8888 | http://localhost:8888 |
| Health Check | 8888 | http://localhost:8888/health |

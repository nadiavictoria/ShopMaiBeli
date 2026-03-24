# ShopMaiBeli — Agentic Shopping Assistant

ShopMaiBeli is an **agentic AI system** that transforms natural language shopping requests into executable workflows to find the **best products at the best price with trustworthy insights**.

Instead of returning a simple list of items, the system:
- generates a **workflow graph (DAG)** of actions,
- executes it with **parallel processing and failure recovery**, and
- returns a **ranked HTML comparison report**.


## What It Does

Example input:
> “Find the best wireless earbuds under $80 with good noise cancellation”

The system will:
1. Generate a workflow (search → analyze → compare → rank)
2. Execute it across multiple data sources
3. Analyze reviews and trust signals
4. Return a structured, ranked report


## Core Idea

ShopMaiBeli treats shopping as a **multi-step reasoning problem**, not a single query.

**Pipeline:**

```
User Input
   ↓
Workflow Generation (LLM)
   ↓
Workflow JSON (DAG)
   ↓
Visualization (n8n-style)
   ↓
Execution Engine
   ↓
HTML Report Output
```


## System Architecture

### 1. Frontend — Chainlit
- Chat interface
- Workflow visualization (n8n-style graph)
- Streaming execution updates
- HTML report preview

### 2. Backend — FastAPI
- `/get_workflow` → generate workflow JSON
- `/run_workflow` → execute workflow with streaming results

### 3. Workflow Generator (LLM)
- Fine-tuned **Qwen-2.5 3B (LoRA)**
- Converts user queries → valid workflow JSON

### 4. Execution Engine
- Parses workflow JSON
- Builds dependency graph
- Executes nodes using:
  - topological sorting
  - parallel execution (`asyncio`)
  - retry + failure recovery

### 5. External Services
- Product APIs (FakeStoreAPI, DummyJSON)
- LLM APIs (DeepSeek)
- Vector DB (FAISS for review analysis)


## Key Features

### Adaptive Workflow Generation
- Simple queries → lightweight pipelines
- Complex queries → multi-branch DAGs

### Parallel Execution
- Independent nodes run concurrently
- Reduces latency significantly

### Modular Node System
Examples:
- `ProductSearch`
- `ReviewAnalyzer (RAG)`
- `TrustScorer`
- `ReportGenerator`

### Failure Recovery
- Retries with exponential backoff
- Graceful degradation if APIs fail

### Trust-Based Ranking
- Combines:
  - ratings
  - review sentiment
  - price-quality ratio
  - seller reputation


## Project Structure (Initial)

```
shopmaibeli/
│
├── frontend/              # Chainlit UI
├── backend/               # FastAPI server
├── workflow_engine/       # DAG execution logic
├── nodes/                 # Custom node implementations
├── models/                # SFT model + inference configs
├── data/                  # Training + RAG data
│
├── docs/
│   ├── requirements.md
│   ├── architecture.md
│   ├── implementation-plan.md
│   ├── nodes.md
│   ├── testing.md
│   └── security.md
│
├── main.py
├── requirements.txt
└── README.md
```


## Tech Stack

| Layer | Technology |
|------|-----------|
| Frontend | Chainlit |
| Backend | FastAPI + httpx |
| LLM (workflow) | Qwen-2.5 3B + LoRA |
| Model Serving | vLLM |
| Node LLM | DeepSeek API |
| Vector DB | FAISS |
| Embeddings | sentence-transformers |
| Execution | asyncio |
| Visualization | n8n-style graph |


## 🛠️ Getting Started (Planned)

```bash
# clone repo
git clone https://github.com/nadiavictoria/ShopMaiBeli.git
cd shopmaibeli

# install dependencies
pip install -r requirements.txt

# run backend
uvicorn main:app --reload

# run frontend
chainlit run app.py
```

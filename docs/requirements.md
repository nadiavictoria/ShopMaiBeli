# Requirements: Workflow Generation

## Goal

Given a natural language shopping request, generate a valid n8n Workflow JSON that the execution engine can parse and run.

## Input / Output

- **Input:** User's shopping query as plain text (e.g., "Find the best laptop under $1000 with good reviews")
- **Output:** Valid n8n Workflow JSON containing nodes, connections, and parameters

## Supported Node Types

The model must generate workflows using only these registered node types:

| Node Type String | Class | Category | When to Use |
|---|---|---|---|
| `chatTrigger` | ChatTriggerExecutor | Main Flow | Always first node — receives user input |
| `agent` | AgentExecutor | Main Flow | Any LLM reasoning step (QueryAnalyzer, TrustScorer, ReportGenerator) |
| `productSearch` | ProductSearchExecutor | Main Flow | Fetching product data from APIs |
| `reviewAnalyzer` | ReviewAnalyzerExecutor | Main Flow | RAG-based review analysis |
| `convertToFile` | ConvertToFileExecutor | Main Flow | Always last node — converts output to HTML file |
| `lmChatDeepSeek` | DeepSeekExecutor | AI Sub-node | Attached to agent nodes as language model |
| `memoryBufferWindow` | MemoryBufferExecutor | AI Sub-node | Conversation memory for agents |
| `outputParserStructured` | OutputParserExecutor | AI Sub-node | Structured HTML output for ReportGenerator |

## Workflow JSON Schema

Must follow n8n format. Minimum required fields:

```json
{
  "name": "ShopMaiBeli Shopping Workflow",
  "nodes": [
    {
      "id": "unique-uuid",
      "name": "Human-readable node name",
      "type": "@n8n/n8n-nodes-langchain.chatTrigger",
      "typeVersion": 1.4,
      "position": [x, y],
      "parameters": {}
    }
  ],
  "connections": {
    "Source Node Name": {
      "main": [
        [{"node": "Target Node Name", "type": "main", "index": 0}]
      ]
    }
  }
}
```

### Connection types

- `main` — primary data flow between main-flow nodes
- `ai_tool` — tool sub-node → agent
- `ai_memory` — memory sub-node → agent
- `ai_languageModel` — LLM sub-node → agent
- `ai_outputParser` — output parser sub-node → agent

## Validation Rules

Before passing to the execution engine, validate:

1. JSON is parseable
2. Has `name`, `nodes`, and `connections` keys
3. Exactly one `chatTrigger` node exists
4. At least one `convertToFile` node exists
5. All nodes referenced in `connections` exist in `nodes`
6. All node `type` strings end with a registered node type
7. No orphan nodes (every non-trigger node has at least one incoming connection)
8. Graph is a valid DAG (no cycles)

## SFT Training Data

Each training example is a pair:

```json
{
  "instruction": "User wants to: Find the best wireless earbuds under $80 with noise cancellation",
  "output": "<complete n8n Workflow JSON>"
}
```

### Sources

1. **n8n template library** — adapt templates from n8n.io/workflows for shopping
2. **Hand-crafted** — 20-30 shopping workflows covering simple price search, multi-source comparison, review-heavy, brand-specific, budget-constrained queries
3. **Synthetic** — generate diverse pairs via DeepSeek API, manually verify each

### SFT config

- Base model: `Qwen/Qwen2.5-3B-Instruct`
- LoRA: `r=64`, `alpha=128`, target all linear layers
- Epochs: 3, LR: `2e-4`
- Framework: HuggingFace Transformers + PEFT + TRL
- Training location: Vast.ai RTX 5080 ($8 budget)

## Model Serving

- Serve via vLLM on Vast.ai
- Expose OpenAI-compatible `/v1/chat/completions` endpoint
- Backend calls this from `backend/main.py` `/get_workflow` route

## Integration Point

Modify `backend/main.py`:

```python
# BEFORE (starter kit): loads static JSON
def generate_workflow(payload: dict) -> dict:
    with open("./NUS News ChatBot.json", "r") as f:
        return json.load(f)

# AFTER: calls SFT model
def generate_workflow(payload: dict) -> dict:
    user_query = extract_query(payload)
    workflow_json = call_sft_model(user_query)
    validate_workflow(workflow_json)
    return workflow_json
```

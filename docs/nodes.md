# Node Specifications

## Overview

Every node executor inherits from `BaseNodeExecutor` (in `nodes/base.py`) and implements:
- `async execute(input_data: NodeInput, context: ExecutionContext) -> NodeOutput`
- `get_notification(output, context) -> NodeNotification` (optional)

Nodes are registered in `nodes/__init__.py` via `NODE_EXECUTOR_REGISTRY`.

---

## Existing Nodes (reuse from starter kit)

### ChatTrigger
- **File:** `nodes/chat_trigger.py`
- **Type string:** `chatTrigger`
- **Role:** Entry point. Extracts latest user message from `context.chat_history`.
- **Output:** `{"chatInput": "user message text", "sessionId": "..."}`
- **No changes needed.**

### Agent (AgentExecutor)
- **File:** `nodes/agent.py`
- **Type string:** `agent`
- **Role:** LLM-powered agent with tool-calling loop. Connects to sub-nodes (LLM, memory, tools, output parser).
- **Key parameters:**
  - `options.systemMessage` — the system prompt that defines the agent's behavior
  - `promptType` — "define" to use a custom text template, otherwise uses `chatInput`
  - `hasOutputParser` — whether to parse output through attached OutputParser
- **Output:** `{"output": "LLM response text or parsed JSON"}`
- **Used for:** QueryAnalyzer, TrustScorer, ReportGenerator — each is just an Agent with a different `systemMessage` in the workflow JSON.
- **No code changes needed.** Different behaviors are configured in the workflow JSON, not in Python.

### ConvertToFile
- **File:** `nodes/convert_to_file.py`
- **Type string:** `convertToFile`
- **Role:** Converts data to downloadable HTML file.
- **Key parameters:**
  - `operation` — "toText"
  - `sourceProperty` — dot-path to extract from input (e.g., "output.html")
  - `options.fileName` — output filename
- **No changes needed.**

### DeepSeek LLM (AI sub-node)
- **File:** `nodes/lm_deepseek.py`
- **Type string:** `lmChatDeepSeek`
- **Role:** Provides `chat_completion()` method to Agent nodes. Not executed in main flow.
- **Requires:** `DEEPSEEK_API_KEY` environment variable in `backend/.env`
- **No changes needed.**

### MemoryBuffer (AI sub-node)
- **File:** `nodes/memory_buffer.py`
- **Type string:** `memoryBufferWindow`
- **Role:** Provides conversation memory to Agent nodes. Stores messages per session.
- **No changes needed.**

### OutputParser (AI sub-node)
- **File:** `nodes/output_parser.py`
- **Type string:** `outputParserStructured`
- **Role:** Parses LLM output into structured JSON. Provides format instructions to agent.
- **Key parameter:** `jsonSchemaExample` — example JSON schema the LLM should output
- **No changes needed.**

### ToolCode (AI sub-node)
- **File:** `nodes/tool_code.py`
- **Type string:** `toolCode`
- **Role:** Executes Python code as a tool for Agent nodes.
- **No changes needed.**

---

## New Nodes (to implement)

### ProductSearch
- **File:** `nodes/product_search.py`
- **Type string:** `productSearch`
- **Role:** Fetches product data from external APIs.

#### Parameters (from workflow JSON)
```json
{
  "source": "fakestoreapi",
  "category": "electronics",
  "query": "",
  "maxResults": 10
}
```

- `source` — which API to call: `"fakestoreapi"`, `"dummyjson"`, or `"mock"` (hardcoded test data)
- `category` — optional category filter
- `query` — search query (can also come from input data via expression `={{ $json.chatInput }}`)
- `maxResults` — max products to return

#### Input
Receives data from parent node (typically QueryAnalyzer or ChatTrigger):
```json
{"chatInput": "wireless earbuds under $80", "category": "electronics", "budget": 80}
```

Or simply the raw user query if no QueryAnalyzer is used.

#### Output
```json
{
  "products": [
    {
      "name": "Sony WF-1000XM5",
      "price": 79.99,
      "rating": 4.5,
      "description": "...",
      "source": "fakestoreapi",
      "url": "https://..."
    }
  ],
  "source": "fakestoreapi",
  "count": 5
}
```

#### API Integration

**FakeStoreAPI** (https://fakestoreapi.com):
```python
import httpx

async def fetch_fakestoreapi(category=None, max_results=10):
    url = "https://fakestoreapi.com/products"
    if category:
        url += f"/category/{category}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=15)
        products = resp.json()[:max_results]
    return [{"name": p["title"], "price": p["price"],
             "rating": p.get("rating", {}).get("rate", 0),
             "description": p["description"],
             "source": "fakestoreapi"} for p in products]
```

**DummyJSON** (https://dummyjson.com/products):
```python
async def fetch_dummyjson(query="", category=None, max_results=10):
    if query:
        url = f"https://dummyjson.com/products/search?q={query}&limit={max_results}"
    elif category:
        url = f"https://dummyjson.com/products/category/{category}?limit={max_results}"
    else:
        url = f"https://dummyjson.com/products?limit={max_results}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=15)
        data = resp.json()
    return [{"name": p["title"], "price": p["price"],
             "rating": p["rating"],
             "description": p["description"],
             "source": "dummyjson"} for p in data.get("products", [])]
```

**Mock data** (for testing without network):
```python
def get_mock_products():
    return [
        {"name": "Test Earbuds Pro", "price": 49.99, "rating": 4.2,
         "description": "Great noise cancellation", "source": "mock"},
        {"name": "Budget Earbuds", "price": 29.99, "rating": 3.8,
         "description": "Good value option", "source": "mock"},
    ]
```

#### Skeleton

```python
class ProductSearchExecutor(BaseNodeExecutor):
    node_type = "productSearch"

    async def execute(self, input_data: NodeInput, context: ExecutionContext) -> NodeOutput:
        source = self.get_parameter("source", "fakestoreapi")
        category = self.get_parameter("category", None)
        max_results = self.get_parameter("maxResults", 10)

        # Get query from input or parameter
        input_json = input_data.first_json
        query = input_json.get("chatInput", "") or input_json.get("query", "")

        # Fetch products based on source
        if source == "fakestoreapi":
            products = await fetch_fakestoreapi(category, max_results)
        elif source == "dummyjson":
            products = await fetch_dummyjson(query, category, max_results)
        else:
            products = get_mock_products()

        return self.create_output({
            "products": products,
            "source": source,
            "count": len(products)
        })
```

---

### ReviewAnalyzer
- **File:** `nodes/review_analyzer.py`
- **Type string:** `reviewAnalyzer`
- **Role:** Analyzes product reviews. Two modes: LLM-based summarization (simple) or RAG with FAISS (advanced).

#### Input
Receives product data from ProductSearch:
```json
{"products": [...], "source": "fakestoreapi", "count": 5}
```

#### Output
```json
{
  "products": [
    {
      "name": "Sony WF-1000XM5",
      "price": 79.99,
      "rating": 4.5,
      "review_summary": "Excellent noise cancellation, comfortable fit, premium sound quality. Some users report occasional Bluetooth connectivity issues.",
      "review_sentiment": "positive",
      "review_confidence": 0.85
    }
  ]
}
```

#### Simple mode (LLM-based)

Use DeepSeek API to generate review summaries from product descriptions and ratings:

```python
class ReviewAnalyzerExecutor(BaseNodeExecutor):
    node_type = "reviewAnalyzer"

    async def execute(self, input_data: NodeInput, context: ExecutionContext) -> NodeOutput:
        input_json = input_data.first_json
        products = input_json.get("products", [])

        # Merge products from multiple sources if needed
        all_items = input_data.get_items(port=0)
        if len(all_items) > 1:
            products = []
            for item in all_items:
                products.extend(item.json_data.get("products", []))

        analyzed = []
        for product in products:
            summary = await self._analyze_product(product)
            analyzed.append({**product, **summary})

        return self.create_output({"products": analyzed})

    async def _analyze_product(self, product):
        # Simple mode: use product data to generate review insight
        # Advanced mode: query FAISS index for real reviews
        return {
            "review_summary": f"Based on {product.get('rating', 'N/A')} star rating...",
            "review_sentiment": "positive" if product.get("rating", 0) >= 4 else "mixed",
            "review_confidence": min(product.get("rating", 0) / 5.0, 1.0)
        }
```

#### Advanced mode (RAG with FAISS)

For the advanced version, build a FAISS index over product reviews stored in `data/reviews/`:

```python
# Build index (run once)
from sentence_transformers import SentenceTransformer
import faiss, json

model = SentenceTransformer("all-MiniLM-L6-v2")
reviews = json.load(open("data/reviews/reviews.json"))
texts = [r["text"] for r in reviews]
embeddings = model.encode(texts)
index = faiss.IndexFlatIP(embeddings.shape[1])
index.add(embeddings)

# Query at runtime
query = f"{product['name']} review"
q_emb = model.encode([query])
scores, indices = index.search(q_emb, k=5)
relevant_reviews = [reviews[i] for i in indices[0]]
```

---

## How Agent Nodes Become Different Roles

The QueryAnalyzer, TrustScorer, and ReportGenerator are all `AgentExecutor` instances. Their behavior is configured entirely in the **Workflow JSON** via `parameters.options.systemMessage`. No Python code changes needed.

### QueryAnalyzer agent — system message example
```
You are a shopping query analyzer. Extract structured parameters from the user's request:
- product_category
- budget (max price)
- priorities (e.g., noise cancellation, battery life)
- preferred_brands (if mentioned)
Respond with a JSON object containing these fields.
```

### TrustScorer agent — system message example
```
You are a product trust evaluator. Given product data and review analysis, score each product on a 0-100 trust scale considering: rating, review sentiment, price-to-quality ratio. Output a JSON array with each product's name, trust_score, and justification.
```

### ReportGenerator agent — system message example
```
You are an HTML report generator. Given scored product data, create a comparison report as valid HTML with: a summary table, ranked product cards, price comparison, and trust justifications. Output only the HTML.
```

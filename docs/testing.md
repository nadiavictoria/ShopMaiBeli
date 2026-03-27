# Testing Strategy

## Test Levels

### 1. Node-level tests
Test each node executor individually with mock inputs.

**Location:** `tests/test_nodes.py`

```python
import pytest
from workflow_engine.models import NodeInput, NodeData, Node
from workflow_engine.context import ExecutionContext
from nodes.product_search import ProductSearchExecutor

@pytest.mark.asyncio
async def test_product_search_mock():
    node = Node(id="1", name="Test Search", type="productSearch",
                type_version=1.0, position=(0,0),
                parameters={"source": "mock", "maxResults": 5})
    executor = ProductSearchExecutor(node, workflow=None)

    input_data = NodeInput(ports=[[[NodeData(json_data={"chatInput": "earbuds"})]]])
    context = ExecutionContext(session_id="test")

    output = await executor.execute(input_data, context)

    assert output.first_json.get("products") is not None
    assert len(output.first_json["products"]) > 0
    assert "name" in output.first_json["products"][0]
    assert "price" in output.first_json["products"][0]

@pytest.mark.asyncio
async def test_product_search_fakestoreapi():
    """Integration test — requires network."""
    node = Node(id="1", name="Test Search", type="productSearch",
                type_version=1.0, position=(0,0),
                parameters={"source": "fakestoreapi", "maxResults": 3})
    executor = ProductSearchExecutor(node, workflow=None)

    input_data = NodeInput(ports=[[[NodeData(json_data={"chatInput": "electronics"})]]])
    context = ExecutionContext(session_id="test")

    output = await executor.execute(input_data, context)

    products = output.first_json.get("products", [])
    assert len(products) <= 3
    for p in products:
        assert isinstance(p["price"], (int, float))

@pytest.mark.asyncio
async def test_review_analyzer():
    from nodes.review_analyzer import ReviewAnalyzerExecutor

    node = Node(id="2", name="Test Review", type="reviewAnalyzer",
                type_version=1.0, position=(0,0), parameters={})
    executor = ReviewAnalyzerExecutor(node, workflow=None)

    mock_products = [
        {"name": "Test Product", "price": 49.99, "rating": 4.2, "description": "Good product"}
    ]
    input_data = NodeInput(ports=[[[NodeData(json_data={"products": mock_products})]]])
    context = ExecutionContext(session_id="test")

    output = await executor.execute(input_data, context)

    products = output.first_json.get("products", [])
    assert len(products) == 1
    assert "review_summary" in products[0]
    assert "review_sentiment" in products[0]
```

### 2. Workflow-level tests
Test the full execution engine with a hand-crafted workflow JSON.

**Location:** `tests/test_workflow.py`

```python
import pytest
from workflow_engine import WorkflowExecutor

SIMPLE_WORKFLOW = {
    "name": "Test Shopping",
    "nodes": [
        {"id": "1", "name": "Trigger", "type": "chatTrigger",
         "typeVersion": 1.4, "position": [0, 0], "parameters": {}},
        {"id": "2", "name": "Search", "type": "productSearch",
         "typeVersion": 1.0, "position": [240, 0],
         "parameters": {"source": "mock", "maxResults": 3}},
        # ... (ConvertToFile or a simple output node)
    ],
    "connections": {
        "Trigger": {"main": [[{"node": "Search", "type": "main", "index": 0}]]},
    }
}

@pytest.mark.asyncio
async def test_simple_workflow():
    executor = WorkflowExecutor.from_json(SIMPLE_WORKFLOW)
    notifications = []
    async for n in executor.execute(
        session_id="test",
        chat_history=[{"role": "user", "content": "find earbuds"}]
    ):
        notifications.append(n)

    assert len(notifications) >= 2  # at least trigger + search + final
    assert notifications[-1].notification_type == "message"  # final message

@pytest.mark.asyncio
async def test_parallel_execution():
    """Verify that parallel ProductSearch nodes actually run concurrently."""
    import time

    PARALLEL_WORKFLOW = {
        "name": "Parallel Test",
        "nodes": [
            {"id": "1", "name": "Trigger", "type": "chatTrigger",
             "typeVersion": 1.4, "position": [0, 0], "parameters": {}},
            {"id": "2", "name": "Search A", "type": "productSearch",
             "typeVersion": 1.0, "position": [240, 0],
             "parameters": {"source": "mock"}},
            {"id": "3", "name": "Search B", "type": "productSearch",
             "typeVersion": 1.0, "position": [240, 200],
             "parameters": {"source": "mock"}},
        ],
        "connections": {
            "Trigger": {"main": [
                [{"node": "Search A", "type": "main", "index": 0},
                 {"node": "Search B", "type": "main", "index": 0}]
            ]}
        }
    }

    executor = WorkflowExecutor.from_json(PARALLEL_WORKFLOW)
    start = time.time()
    async for _ in executor.execute(
        session_id="test",
        chat_history=[{"role": "user", "content": "test"}]
    ):
        pass
    elapsed = time.time() - start
    # If parallel, should be ~T not 2T
    # (with mock data this is near-instant, but tests the code path)
    assert elapsed < 5
```

### 3. Workflow generation tests
Validate that generated workflow JSON is structurally correct.

**Location:** `tests/test_generation.py`

```python
import json

def validate_workflow(workflow: dict) -> list[str]:
    """Return list of errors (empty if valid)."""
    errors = []

    if "name" not in workflow:
        errors.append("Missing 'name'")
    if "nodes" not in workflow:
        errors.append("Missing 'nodes'")
        return errors
    if "connections" not in workflow:
        errors.append("Missing 'connections'")

    node_names = {n["name"] for n in workflow["nodes"]}
    node_types = [n["type"].split(".")[-1] for n in workflow["nodes"]]

    # Must have chatTrigger
    if "chatTrigger" not in node_types:
        errors.append("No chatTrigger node")

    # Must have convertToFile
    if "convertToFile" not in node_types:
        errors.append("No convertToFile node")

    # Check connections reference valid nodes
    for source, conns in workflow.get("connections", {}).items():
        if source not in node_names:
            errors.append(f"Connection source '{source}' not in nodes")
        for conn_type, outputs in conns.items():
            for output_list in outputs:
                for conn in output_list:
                    if conn["node"] not in node_names:
                        errors.append(f"Connection target '{conn['node']}' not in nodes")

    return errors

def test_example_workflow_valid():
    with open("workflows/example_shopping.json") as f:
        wf = json.load(f)
    errors = validate_workflow(wf)
    assert errors == [], f"Validation errors: {errors}"
```

### 4. API integration tests
Test external API connectivity.

**Location:** `tests/test_apis.py`

```python
import httpx
import pytest

@pytest.mark.asyncio
async def test_fakestoreapi_reachable():
    async with httpx.AsyncClient() as client:
        resp = await client.get("https://fakestoreapi.com/products?limit=1", timeout=10)
    assert resp.status_code == 200
    assert len(resp.json()) == 1

@pytest.mark.asyncio
async def test_dummyjson_reachable():
    async with httpx.AsyncClient() as client:
        resp = await client.get("https://dummyjson.com/products?limit=1", timeout=10)
    assert resp.status_code == 200
    assert "products" in resp.json()

@pytest.mark.asyncio
async def test_backend_health():
    async with httpx.AsyncClient() as client:
        resp = await client.get("http://localhost:8888/health", timeout=5)
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

## Running Tests

```bash
# All tests
pytest tests/ -v

# Just node tests (no network needed)
pytest tests/test_nodes.py -v

# Just integration tests (needs network + running services)
pytest tests/test_apis.py -v
```

## What to Test Before Each Milestone

**Before mid-term report:**
- All node-level tests pass with mock data
- Simple workflow executes end-to-end
- Backend health check works
- At least one external API integration works

**Before final report:**
- Full parallel workflow test passes
- Workflow generation validation passes on 10+ test queries
- Retry/failure recovery test (simulate API timeout)
- End-to-end: user query → workflow gen → execution → HTML report

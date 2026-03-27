# Implementation Plan: Execution Engine

## Overview

The execution engine lives in `workflow_engine/`. The starter kit provides a working sequential executor. We extend it with parallel execution and retry logic.

## What to Modify

| File | Change |
|---|---|
| `workflow_engine/executor.py` | Add parallel execution (asyncio.gather) and retry wrapper |
| `nodes/__init__.py` | Register new node types (productSearch, reviewAnalyzer) |
| `backend/main.py` | Update imports, modify `generate_workflow()` to call SFT model |

## What to Create

| File | Purpose |
|---|---|
| `nodes/product_search.py` | ProductSearch node executor |
| `nodes/review_analyzer.py` | ReviewAnalyzer node executor |

## What Stays Unchanged

These files work as-is after migration (only import paths change):

`workflow_engine/models.py`, `workflow_engine/workflow.py`, `workflow_engine/context.py`, `nodes/base.py`, `nodes/agent.py`, `nodes/chat_trigger.py`, `nodes/convert_to_file.py`, `nodes/lm_deepseek.py`, `nodes/memory_buffer.py`, `nodes/output_parser.py`, `nodes/tool_code.py`

---

## Change 1: Parallel Execution

### Current behavior (sequential)

In `workflow_engine/executor.py`, the `execute()` method loops through `execution_order` one at a time:

```python
for node_name in execution_order:
    executor = executor_class(node, self.workflow)
    output = await executor.execute(input_data, context)
    context.set_node_output(node_name, output)
```

### New behavior (parallel where possible)

Group nodes by topological level. Nodes at the same level have no mutual dependencies and can run concurrently.

```python
async def execute(self, session_id, chat_history, files):
    context = self.get_context(session_id)
    context.chat_history = chat_history or []
    context.files = files or []
    context.node_outputs = {}

    levels = self._get_execution_levels()  # NEW: group by topo level

    for level_nodes in levels:
        if len(level_nodes) == 1:
            # Single node — run directly
            yield await self._execute_node(level_nodes[0], context)
        else:
            # Multiple independent nodes — run in parallel
            tasks = [self._execute_node(name, context) for name in level_nodes]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    # handle failure — see Change 2
                    pass
                else:
                    yield result
```

### Helper: `_get_execution_levels()`

```python
def _get_execution_levels(self) -> list[list[str]]:
    """Group topologically sorted nodes into parallel levels."""
    execution_order = self.workflow.get_execution_order()
    levels = []
    placed = set()

    while len(placed) < len(execution_order):
        current_level = []
        for name in execution_order:
            if name in placed:
                continue
            parents = self.workflow.get_parent_nodes(name)
            if all(p in placed for p in parents):
                current_level.append(name)
        for name in current_level:
            placed.add(name)
        levels.append(current_level)

    return levels
```

### Helper: `_execute_node()`

Extract single-node execution into its own method:

```python
async def _execute_node(self, node_name, context):
    node = self.workflow.nodes[node_name]
    executor_class = get_executor_class(node.node_type)
    executor = executor_class(node, self.workflow)
    input_data = context.get_input_for_node(node_name, self.workflow)
    output = await executor.execute(input_data, context)
    context.set_node_output(node_name, output)
    return executor.get_notification(output, context)
```

---

## Change 2: Retry with Exponential Backoff

Wrap `_execute_node()` with retry logic:

```python
async def _execute_node_with_retry(self, node_name, context, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await self._execute_node(node_name, context)
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(f"Node '{node_name}' failed after {max_retries} attempts: {e}")
                # Mark as failed, return error notification
                context.set_node_output(node_name, NodeOutput.single({"error": str(e)}))
                return NodeNotification(
                    node_name=node_name,
                    session_id=context.session_id,
                    message=f"Node failed: {e}",
                    notification_type="step"
                )
            wait = 2 ** attempt  # 1s, 2s, 4s
            logger.warning(f"Node '{node_name}' attempt {attempt+1} failed, retrying in {wait}s")
            await asyncio.sleep(wait)
```

Then use `_execute_node_with_retry` instead of `_execute_node` in the main loop.

---

## Change 3: Register New Nodes

In `nodes/__init__.py`, add:

```python
from .product_search import ProductSearchExecutor
from .review_analyzer import ReviewAnalyzerExecutor

NODE_EXECUTOR_REGISTRY = {
    # existing
    "chatTrigger": ChatTriggerExecutor,
    "memoryBufferWindow": MemoryBufferExecutor,
    "toolCode": ToolCodeExecutor,
    "outputParserStructured": OutputParserExecutor,
    "convertToFile": ConvertToFileExecutor,
    "agent": AgentExecutor,
    "lmChatDeepSeek": DeepSeekExecutor,
    # new
    "productSearch": ProductSearchExecutor,
    "reviewAnalyzer": ReviewAnalyzerExecutor,
}
```

---

## Change 4: Update backend/main.py

```python
# Update imports
from workflow_engine import WorkflowExecutor

# Modify generate_workflow to call model instead of loading file
def generate_workflow(payload: dict) -> dict:
    chat_history = payload.get("chat_history", [])
    user_query = ""
    for msg in reversed(chat_history):
        if msg.get("role") == "user":
            user_query = msg.get("content", "")
            break

    if not user_query:
        # fallback: load example workflow
        with open("./workflows/example_shopping.json", "r") as f:
            return json.load(f)

    workflow_json = call_workflow_generator(user_query)
    validate_workflow(workflow_json)
    return workflow_json
```

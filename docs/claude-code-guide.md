# Claude Code Guide for ShopMaiBeli

## Overview

This guide explains how to use Claude Code effectively to build ShopMaiBeli. Each task is scoped so you can paste it as a prompt and get working code back.

## Setup

Make sure Claude Code has access to the repo root. It needs to read the existing files to understand the codebase before modifying anything.

## Task Templates

### Task 1: Migrate starter kit to new structure

```
I'm migrating the NUS News ChatBot starter kit to a new project structure.

Current structure: chatbot/, server/workflow/, server/workflow/nodes/
Target structure: frontend/, backend/, workflow_engine/, nodes/

Read docs/architecture.md for the full migration map.

Steps:
1. Copy files to their new locations per the migration map
2. Update all import paths (see "Import changes after migration" in architecture.md)
3. Update start.sh and stop.sh to reference new paths
4. Convert environment.yml to requirements.txt
5. Test that `python backend/main.py` starts without import errors

Do NOT modify any logic — only move files and fix imports.
```

### Task 2: Implement ProductSearch node

```
Read docs/nodes.md section "ProductSearch" for the full specification.

Create nodes/product_search.py that:
1. Inherits from BaseNodeExecutor (in nodes/base.py)
2. Has node_type = "productSearch"
3. Reads parameters: source, category, maxResults from node config
4. Gets query from input_data.first_json (chatInput or query key)
5. Calls the appropriate API based on source parameter:
   - "fakestoreapi" → GET https://fakestoreapi.com/products
   - "dummyjson" → GET https://dummyjson.com/products/search?q=...
   - "mock" → return hardcoded test data
6. Returns NodeOutput with {"products": [...], "source": "...", "count": N}
7. Includes a get_notification() that reports how many products were found

Also register it in nodes/__init__.py as "productSearch": ProductSearchExecutor

Use httpx for async HTTP calls with timeout=15.
```

### Task 3: Implement ReviewAnalyzer node

```
Read docs/nodes.md section "ReviewAnalyzer" for the full specification.

Create nodes/review_analyzer.py that:
1. Inherits from BaseNodeExecutor
2. Has node_type = "reviewAnalyzer"
3. Takes product data from input (may come from multiple ProductSearch nodes)
4. For each product, generates a review summary, sentiment, and confidence score
5. Simple mode: derive from product rating and description (no external calls)
6. Returns NodeOutput with {"products": [...]} where each product has review_summary, review_sentiment, review_confidence added

Also register it in nodes/__init__.py as "reviewAnalyzer": ReviewAnalyzerExecutor
```

### Task 4: Add parallel execution to executor

```
Read docs/implementation-plan.md "Change 1: Parallel Execution" for the full spec.

Modify workflow_engine/executor.py to:
1. Add _get_execution_levels() method that groups topologically sorted nodes into parallel levels
2. Add _execute_node() helper that extracts single-node execution logic
3. Modify execute() to iterate over levels instead of individual nodes
4. For levels with multiple nodes, use asyncio.gather() to run them concurrently
5. For levels with one node, run directly (no gather overhead)
6. Yield notifications as before

Keep all existing error handling and logging.
Do NOT change models.py, workflow.py, or context.py.
```

### Task 5: Add retry logic

```
Read docs/implementation-plan.md "Change 2: Retry with Exponential Backoff" for the spec.

Add _execute_node_with_retry() method to WorkflowExecutor in workflow_engine/executor.py:
1. Wraps _execute_node() with try/except
2. Retries up to 3 times with exponential backoff (1s, 2s, 4s)
3. On final failure: logs error, sets node output to {"error": "..."}, returns error notification
4. Use this method instead of _execute_node() in the main execution loop
```

### Task 6: Create example workflow JSON

```
Read docs/requirements.md for the Workflow JSON schema and docs/nodes.md for node types.

Create workflows/example_shopping.json — a complete n8n workflow for:
"Find the best wireless earbuds under $80 with noise cancellation and good reviews"

The workflow should have:
1. chatTrigger (entry point)
2. agent "QueryAnalyzer" with lmChatDeepSeek sub-node
3. Two productSearch nodes (fakestoreapi + dummyjson) — both connected from QueryAnalyzer
4. reviewAnalyzer — connected from both productSearch nodes
5. agent "TrustScorer" with lmChatDeepSeek sub-node
6. agent "ReportGenerator" with lmChatDeepSeek + outputParserStructured sub-nodes
7. convertToFile (final output)

Include proper UUIDs, positions, connections (main + ai_languageModel + ai_outputParser), and system messages for each agent.
```

### Task 7: Modify backend for workflow generation

```
Read docs/requirements.md "Integration Point" section.

Modify backend/main.py to:
1. Update imports from workflow_engine instead of workflow
2. Replace generate_workflow() — instead of loading a static JSON file, it should:
   a. Extract the user query from payload chat_history
   b. Call the SFT model (or DeepSeek API for now) with the system prompt from models/prompts/workflow_gen.txt
   c. Parse the response as JSON
   d. Validate the workflow structure
   e. Return the validated workflow JSON
3. Add a validate_workflow() function that checks the rules from docs/requirements.md
4. Fallback: if generation fails, load workflows/example_shopping.json

For now, use DeepSeek API directly (same DEEPSEEK_API_KEY). We'll swap to vLLM later.
```

### Task 8: Write tests

```
Read docs/testing.md for the full testing strategy.

Create:
1. tests/test_nodes.py — unit tests for ProductSearch (mock) and ReviewAnalyzer
2. tests/test_workflow.py — integration test running a simple workflow end-to-end
3. tests/test_generation.py — validate_workflow() function + test against example JSON

Use pytest + pytest-asyncio. Mock data only for unit tests (no network needed).
```

### Task 9: Connect frontend to backend

```
The frontend is frontend/app.py (Chainlit). It already works with the starter kit's backend.

After migration, verify:
1. The base_url default still points to http://localhost:8888
2. get_workflow command calls /get_workflow and renders the n8n visualization
3. run_workflow command calls /run_workflow and streams NDJSON progress
4. HtmlPreview component renders the final HTML report in the sidebar

Update the app name in frontend/.chainlit/config.toml to "ShopMaiBeli".
Update frontend/chainlit.md with a ShopMaiBeli welcome message.
```

## General Tips for Claude Code

1. **Always reference the docs.** Start prompts with "Read docs/X.md for the spec" so Claude Code understands the context.

2. **One task at a time.** Don't ask for migration + new nodes + parallel execution in one prompt. Each task above is scoped to be a single Claude Code session.

3. **Test after each task.** Run `python backend/main.py` after migration to check imports. Run `pytest tests/test_nodes.py` after implementing nodes.

4. **Give it the file first.** If modifying an existing file, paste the current contents or tell Claude Code to read it first. It needs to see the current code to make correct edits.

5. **Be specific about what NOT to change.** E.g., "Do NOT change models.py" prevents unnecessary refactoring.

## Recommended Task Order

1. Task 1 — Migrate structure (must be first)
2. Task 2 — ProductSearch node
3. Task 3 — ReviewAnalyzer node
4. Task 6 — Example workflow JSON
5. Task 8 — Tests (run them now to verify nodes work)
6. Task 4 — Parallel execution
7. Task 5 — Retry logic
8. Task 7 — Backend workflow generation
9. Task 9 — Frontend polish

# Prompt Engineering: Workflow Generation

## System Prompt

```
You are a workflow generation assistant for ShopMaiBeli, an agentic shopping system.
Given a user's shopping request, generate a valid n8n Workflow JSON.

Available node types:
- chatTrigger: Entry point, receives user message. Always first node.
- agent: LLM-powered reasoning node. Use for query analysis, trust scoring, report
  generation. Configure via "options.systemMessage". Must have a lmChatDeepSeek
  sub-node connected via ai_languageModel.
- productSearch: Searches product APIs. Configure via "parameters.source"
  (e.g., "fakestoreapi", "dummyjson") and optional "parameters.category".
- reviewAnalyzer: RAG-based review analysis. Takes product data as input.
- convertToFile: Converts to downloadable HTML. Always last node.
  Set "parameters.sourceProperty" to "output.html".
- lmChatDeepSeek: AI sub-node for LLM. Connect via ai_languageModel.
- memoryBufferWindow: AI sub-node for memory. Connect via ai_memory.
- outputParserStructured: AI sub-node for structured output. Connect via ai_outputParser.

Rules:
1. Always start with chatTrigger, always end with convertToFile
2. Use "main" connections for data flow between main-flow nodes
3. Use ai_languageModel/ai_memory/ai_outputParser for sub-node connections
4. Each agent node MUST have at least one lmChatDeepSeek sub-node
5. Position nodes left-to-right: x increments by ~240, sub-nodes at y + 200
6. Generate unique UUIDs for each node id
7. Output ONLY valid JSON — no markdown, no explanation

Simple queries → minimal pipeline:
  chatTrigger → productSearch → agent(ReportGenerator) → convertToFile

Complex queries → full pipeline:
  chatTrigger → agent(QueryAnalyzer) → [productSearch(A), productSearch(B)]
  → reviewAnalyzer → agent(TrustScorer) → agent(ReportGenerator) → convertToFile
```

## Few-Shot Examples

### Example 1: Simple price search
**Query:** "Find the cheapest mechanical keyboard"
**Structure:** `chatTrigger → productSearch → agent(Report) + outputParser + LLM → convertToFile`

### Example 2: Multi-source with reviews
**Query:** "Compare wireless earbuds under $80 from multiple sources with review analysis"
**Structure:** `chatTrigger → agent(QueryAnalyzer) + LLM → [productSearch(A), productSearch(B)] → reviewAnalyzer → agent(TrustScorer) + LLM → agent(Report) + outputParser + LLM → convertToFile`

### Example 3: Brand-specific trust search
**Query:** "Find the most trusted Sony headphones with good noise cancellation"
**Structure:** `chatTrigger → agent(QueryAnalyzer) + LLM → productSearch → reviewAnalyzer → agent(TrustScorer) + LLM → agent(Report) + outputParser + LLM → convertToFile`

## Prompt Improvement Loop

1. Generate a workflow JSON from a test query
2. Validate against rules in `requirements.md`
3. Try to execute it with the execution engine
4. If it fails, identify the error and patch the prompt
5. Log `(query, generated JSON, pass/fail)` as potential SFT training data

## Common Failures and Fixes

| Failure | Prompt Fix |
|---|---|
| Missing LLM sub-node on agent | "Each agent MUST have at least one lmChatDeepSeek sub-node" |
| Invalid connection type string | Explicit list of valid connection type strings |
| Node in connections doesn't exist in nodes array | "All node names in connections must match a node in nodes" |
| JSON wrapped in markdown code block | "Output ONLY valid JSON — no markdown" |
| convertToFile sourceProperty wrong | Explicit example: `"sourceProperty": "output.html"` |
| Duplicate node names | "Each node must have a unique name" |

## Quality Metrics

| Metric | What It Measures |
|---|---|
| Valid JSON rate | % of outputs that parse as JSON |
| Schema valid rate | % that pass all validation rules |
| Executable rate | % the engine can run without errors |
| Semantic quality | Manual check — does the workflow make sense for the query? |

## Collecting SFT Training Data

1. Write 10-15 diverse shopping queries at different complexity levels
2. Use the system prompt with DeepSeek API to generate a workflow for each
3. Manually fix any errors in the generated JSON
4. Validate each by running through the execution engine
5. Save as `{"instruction": "...", "output": "..."}` pairs in `data/workflows/`
6. Augment with query variations (swap product names, budgets, priorities)
7. Target: 50-100 high-quality examples

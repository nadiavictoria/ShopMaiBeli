# Security Considerations

## API Keys

### Storage
- All API keys stored in `backend/.env` (gitignored)
- Never commit keys to the repository
- `.env` format: `DEEPSEEK_API_KEY=sk-...`

### Required keys
| Key | Used By | Purpose |
|---|---|---|
| `DEEPSEEK_API_KEY` | `nodes/lm_deepseek.py` | LLM calls within workflow nodes |
| `VLLM_API_URL` (optional) | `backend/main.py` | SFT model endpoint on Vast.ai |

### .gitignore entries
```
backend/.env
*.env
.env.*
```

## Code Execution

### ToolCode node
The `nodes/tool_code.py` executor runs arbitrary Python code via `exec()`. This is inherited from the starter kit and is a known security risk.

**Mitigations:**
- Only used for pre-defined tool functions in workflow JSONs we control
- Never expose the ToolCode node to user-supplied code
- In production, this would need sandboxing (e.g., subprocess with resource limits)

### Product API calls
- `nodes/product_search.py` makes HTTP requests to external APIs
- Always set timeouts (`timeout=15` in httpx)
- Validate response status codes before parsing
- Never pass user input directly into URLs without sanitization

## Input Validation

### Workflow JSON
- Validate structure before execution (see `requirements.md` validation rules)
- Reject workflows with unregistered node types
- Reject workflows with cycles (topological sort catches this)
- Limit maximum number of nodes (e.g., 20) to prevent resource exhaustion

### User input
- User queries are passed as strings through the ChatTrigger node
- No special sanitization needed — they're used as LLM prompts, not executed as code
- HTML report output is rendered in a sandboxed iframe (HtmlPreview.jsx) — no XSS risk to the main page

## Network Security

### CORS
The backend has CORS set to `allow_origins=["*"]` (from starter kit). For production:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000"],  # restrict to frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Rate limiting
- External API calls should respect rate limits
- FakeStoreAPI and DummyJSON are free — no auth needed, but may throttle
- DeepSeek API has rate limits tied to the API key tier
- Retry logic with exponential backoff (in `workflow_engine/executor.py`) handles this

## Data Privacy

- No user data is persisted beyond the session
- Conversation memory (`workflow_engine/context.py`) is stored in-memory only
- Session contexts are keyed by session_id and can be cleared via `executor.clear_context()`
- Product API queries do not contain personally identifiable information

## Dependencies

Keep dependencies minimal and pinned:
```
chainlit==2.9.6
fastapi[standard]
httpx
openai
python-dotenv
faiss-cpu
sentence-transformers
```

Run `pip audit` periodically to check for known vulnerabilities.

## Vast.ai Security

- The SFT model runs on a rented Vast.ai GPU instance
- Do not store API keys on the Vast.ai instance beyond what's needed for training
- Use SSH key authentication, not passwords
- Terminate instances when not in use to avoid unauthorized access and cost overrun

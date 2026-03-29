# FastAPI Backend Server

## Overview

This module is a backend service built with [FastAPI](https://fastapi.tiangolo.com), responsible for receiving frontend requests, executing the workflow engine, and returning results. It provides RESTful API endpoints for workflow visualization and execution.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   FastAPI Backend (Port 8888)                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                      main.py                              │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │   │
│  │  │ GET /health │  │POST /get_   │  │ POST /run_      │   │   │
│  │  │ (health     │  │  workflow   │  │   workflow      │   │   │
│  │  │  check)     │  │ (visualize) │  │ (streaming)     │   │   │
│  │  └─────────────┘  └──────┬──────┘  └────────┬────────┘   │   │
│  └──────────────────────────┼──────────────────┼────────────┘   │
│                             │                  │                 │
│  ┌──────────────────────────▼──────────────────▼────────────┐   │
│  │                    n8n_utils.py                           │   │
│  │              (n8n-demo HTML generation)                   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    workflow/                              │   │
│  │              (Workflow Execution Engine)                  │   │
│  │                  See workflow/README.md                   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
server/
├── main.py                   # FastAPI application entry point
├── n8n_utils.py              # n8n visualization HTML generator
├── NUS News ChatBot.json     # n8n workflow definition file
├── .env                      # Environment variables
├── server.log                # Runtime logs
└── workflow/                 # Workflow execution engine (submodule)
    └── ...                   # See workflow/README.md
```

## API Endpoints

### GET /health

Health check endpoint.

**Response:**
```json
{"status": "ok"}
```

### POST /get_workflow

Returns n8n workflow visualization HTML.

**Request Body:** `{}` (optional)

**Response:**
```json
{
    "type": "message",
    "name": "Workflow Preview",
    "text": "Successfully built workflow: **NUS News ChatBot**",
    "html": "<!doctype html>..."
}
```

The HTML response contains an interactive n8n workflow visualization using the `n8n-demo` web component.

### POST /run_workflow

Executes the workflow and returns results as a streaming NDJSON response.

**Request Body:**
```json
{
    "session_id": "user-session-123",
    "chat_history": [
        {"role": "user", "content": "Show me NUS news from last week"},
        {"role": "assistant", "content": "..."}
    ],
    "files": [
        {
            "name": "document.pdf",
            "mime": "application/pdf",
            "size": 1024,
            "content": "base64-encoded-content"
        }
    ]
}
```

**Response:** NDJSON stream (each line is a JSON object)
```
{"type":"step","name":"When chat message received","text":"Received: ...","html":""}
{"type":"step","name":"Analyze Agent","text":"Processing...","html":"<div>...</div>"}
{"type":"message","name":"NUS News ChatBot","text":"Workflow executed successfully.","html":"<html>...</html>"}
```

**Response Headers:**
- `Content-Type: application/x-ndjson`
- `Cache-Control: no-cache`
- `X-Accel-Buffering: no` (prevents proxy buffering)

## Core Code Analysis

### main.py Key Components

| Component | Responsibility |
|-----------|----------------|
| `app` | FastAPI application instance |
| `generate_workflow()` | Load workflow JSON file |
| `get_workflow_executor()` | Get/create workflow executor (singleton) |
| `run_workflow()` | Stream workflow execution results |

### Streaming Response Implementation

```python
async def stream():
    async for notification in get_workflow_executor().execute(
        session_id, chat_history, files
    ):
        yield notification.to_json()

return StreamingResponse(
    stream(),
    media_type="application/x-ndjson",
    headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    },
)
```

### n8n_utils.py

Generates HTML pages containing the n8n-demo Web Component for workflow visualization:

```python
def build_n8n_demo_html(workflow: dict) -> str:
    # Uses n8n-demo component to render workflow
    # Includes JavaScript for auto-loading and button click handling
```

## Workflow JSON Structure

The workflow is defined in n8n JSON format:

```json
{
    "name": "NUS News ChatBot",
    "nodes": [
        {
            "id": "unique-node-id",
            "name": "When chat message received",
            "type": "@n8n/n8n-nodes-langchain.chatTrigger",
            "parameters": {
                "options": {}
            },
            "position": [0, 0]
        }
    ],
    "connections": {
        "Source Node": {
            "main": [
                [{"node": "Target Node", "type": "main", "index": 0}]
            ]
        }
    }
}
```

### Node Types Used

| Node Type | Description |
|-----------|-------------|
| `chatTrigger` | Entry point, receives chat messages |
| `agent` | AI Agent with tool calling capability |
| `memoryBufferWindow` | Conversation memory buffer |
| `toolCode` | Python code execution tool |
| `lmChatDeepSeek` | DeepSeek LLM integration |
| `outputParserStructured` | Structured output parser |
| `convertToFile` | Convert data to file format |

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DEEPSEEK_API_KEY` | API key for DeepSeek LLM | Yes |

Create a `.env` file in the server directory:
```
DEEPSEEK_API_KEY=your-api-key-here
```

## Extension Guide

### Adding New API Endpoints

```python
from fastapi import Body

@app.post("/new_endpoint")
async def new_endpoint(payload: dict = Body(default={})):
    # Implementation logic
    return {"result": "..."}
```

### Loading Different Workflows

Modify `generate_workflow()` to support multiple workflows:

```python
def generate_workflow(workflow_name: str = "default") -> dict:
    file_path = f"./{workflow_name}.json"
    with open(file_path, "r") as f:
        return json.load(f)
```

### Adding Authentication Middleware

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

@app.post("/protected")
async def protected_endpoint(token = Depends(security)):
    # Validate token
    if not validate_token(token.credentials):
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"message": "Authenticated"}
```

### Adding CORS for Specific Origins

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "https://your-domain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Running the Application

```bash
# Development mode (foreground)
cd server
python main.py

# Using uvicorn directly
uvicorn main:app --host 0.0.0.0 --port 8888 --reload

# Production mode (background)
python main.py > server.log 2>&1 &
```

## Testing the API

```bash
# Health check
curl http://localhost:8888/health

# Get workflow visualization
curl -X POST http://localhost:8888/get_workflow \
  -H "Content-Type: application/json" \
  -d '{}'

# Run workflow
curl -X POST http://localhost:8888/run_workflow \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-session",
    "chat_history": [{"role": "user", "content": "Show me NUS news"}],
    "files": []
  }'
```

## Learning Resources

- [FastAPI Official Documentation](https://fastapi.tiangolo.com)
- [FastAPI Streaming Responses](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)
- [n8n-demo Component](https://www.npmjs.com/package/@n8n_io/n8n-demo-component)
- [NDJSON Specification](http://ndjson.org)

# Chainlit Chat Frontend

## Overview

This module is a chat interface built with the [Chainlit](https://docs.chainlit.io) framework, serving as the entry point for users to interact with the backend workflow engine. Chainlit is a Python framework designed for building AI chat applications, providing out-of-the-box chat UI, session management, and file upload capabilities.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Chainlit Frontend (Port 8000)               │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐  │
│  │     UI      │ ←→ │   Session   │ ←→ │   HTTP Client   │  │
│  │   (React)   │    │  Management │    │    (httpx)      │  │
│  └─────────────┘    └─────────────┘    └────────┬────────┘  │
│                                                  │           │
│  ┌─────────────────────────────────────────────┐│           │
│  │  Custom Element: HtmlPreview (iframe)        ││           │
│  └─────────────────────────────────────────────┘│           │
└──────────────────────────────────────────────────┼───────────┘
                                                   │
                                                   ▼
                                    FastAPI Backend (Port 8888)
```

## Directory Structure

```
chatbot/
├── app.py                    # Main application (core logic)
├── chainlit.md               # Welcome page content
├── chatbot.log               # Runtime logs
├── public/
│   └── elements/
│       └── HtmlPreview.jsx   # Custom HTML preview component
└── .chainlit/
    ├── config.toml           # Chainlit configuration
    └── translations/         # Multi-language translation files
        └── en-US.json
```

## Core Concepts

### 1. Chainlit Lifecycle Hooks

Chainlit uses decorators to define lifecycle hooks that execute code at specific events:

| Decorator | Trigger | Purpose |
|-----------|---------|---------|
| `@cl.on_chat_start` | New session starts | Initialize session, register commands |
| `@cl.on_message` | User message received | Process user input, call backend |
| `@cl.on_settings_update` | User modifies settings | Update configuration (e.g., Base URL) |

```python
@cl.on_chat_start
async def on_chat_start():
    # Session initialization logic
    pass

@cl.on_message
async def on_message(message: cl.Message):
    # Message processing logic
    pass
```

### 2. Command System

This application registers two commands that users can select via the UI:

| Command ID | Icon | Function | Backend Endpoint |
|------------|------|----------|------------------|
| `get_workflow` | hammer | Get workflow visualization | POST /get_workflow |
| `run_workflow` | play | Execute workflow (streaming) | POST /run_workflow |

Command registration code:
```python
commands = [
    {"id": "get_workflow", "icon": "hammer", "description": "...", "persistent": True},
    {"id": "run_workflow", "icon": "play", "description": "...", "persistent": True},
]
await cl.context.emitter.set_commands(commands)
```

### 3. Custom Elements

`HtmlPreview` is a custom React component for safely rendering HTML content in the sidebar:

- **Location**: `public/elements/HtmlPreview.jsx`
- **Function**: Uses iframe sandbox for isolated HTML rendering
- **Display mode**: `display="side"` shows in sidebar

```python
cl.CustomElement(
    name="HtmlPreview",
    props={"html": html_content, "minHeight": 200},
    display="side",
)
```

### 4. Streaming Response Handling (NDJSON)

The backend `/run_workflow` endpoint returns NDJSON (Newline Delimited JSON) format streaming responses, where each line is an independent JSON object:

```python
async for line in resp.aiter_lines():
    data = json.loads(line)
    await _render_event(data)
```

Event structure:
```json
{
    "type": "message" | "step",
    "name": "Node name",
    "text": "Text content",
    "html": "HTML content (optional)"
}
```

## Key Code Analysis

### Core Functions in app.py

| Function | Responsibility |
|----------|----------------|
| `on_chat_start()` | Initialize session, register commands, set Base URL |
| `on_message()` | Route to corresponding handler based on command |
| `_handle_single_response()` | Handle single JSON response (get_workflow) |
| `_handle_streaming_response()` | Handle NDJSON streaming response (run_workflow) |
| `_render_event()` | Render event as Chainlit message or step |
| `_get_files_from_message()` | Extract uploaded files and convert to Base64 |
| `_build_html_elements()` | Build HtmlPreview sidebar elements |

### Request Data Structure

Request body sent to backend:
```json
{
    "session_id": "chainlit-session-id",
    "chat_history": [
        {"role": "user", "content": "User message"},
        {"role": "assistant", "content": "Assistant reply"}
    ],
    "files": [
        {
            "name": "file.txt",
            "mime": "text/plain",
            "size": 1024,
            "content": "base64-encoded-content"
        }
    ]
}
```

## Configuration

### Key config.toml Settings

Configuration file located at `.chainlit/config.toml`:

```toml
[UI]
name = "Agentic Workflow"      # Application name
language = "en-US"             # Interface language

[features.spontaneous_file_upload]
enabled = true                 # Allow file uploads
max_files = 20                 # Maximum number of files
max_size_mb = 500              # Maximum file size (MB)
```

### Runtime Settings

Users can modify the Base URL in the chat interface:
- Default: `http://localhost:8888`
- Storage: `cl.user_session`

## Extension Guide

### Adding New Commands

1. Register the command in `on_chat_start()`:
```python
commands.append({
    "id": "my_command",
    "icon": "star",
    "description": "My new command",
    "persistent": True,
})
```

2. Add routing in `on_message()`:
```python
elif cmd == "my_command":
    url = _join_url(base_url, "my_endpoint")
    await _handle_my_command(url, files)
```

3. Implement the handler function:
```python
async def _handle_my_command(url: str, files: list):
    # Implementation logic
    pass
```

### Adding Custom Components

1. Create a JSX file in `public/elements/`:
```jsx
// public/elements/MyComponent.jsx
export default function MyComponent({ props }) {
    return <div>{props.content}</div>;
}
```

2. Use it in Python code:
```python
cl.CustomElement(
    name="MyComponent",
    props={"content": "Hello"},
    display="inline",  # or "side"
)
```

### Modifying UI Styles

- Edit UI configuration in `.chainlit/config.toml`
- Replace logo images in `public/` directory
- Modify `chainlit.md` to update the welcome page

## Running the Application

```bash
# Development mode (foreground)
cd chatbot
chainlit run app.py --port 8000

# Production mode (background)
chainlit run app.py --port 8000 > chatbot.log 2>&1 &
```

## Learning Resources

- [Chainlit Official Documentation](https://docs.chainlit.io)
- [Chainlit Custom Elements](https://docs.chainlit.io/custom-frontend/custom-elements)
- [httpx Async HTTP Client](https://www.python-httpx.org)

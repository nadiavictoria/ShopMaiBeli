# NUS News ChatBot - Agentic Workflow System

A complete AI-powered chatbot system that demonstrates how to build agentic workflows using a simplified n8n-style workflow engine. This project serves as an educational resource for learning about AI agents, workflow orchestration, and full-stack development.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           NUS News ChatBot System                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Chainlit Frontend (Port 8000)                     │    │
│  │                                                                      │    │
│  │  • Chat UI with message history                                      │    │
│  │  • File upload support                                               │    │
│  │  • Custom HTML preview component                                     │    │
│  │  • Real-time streaming display                                       │    │
│  └──────────────────────────────┬──────────────────────────────────────┘    │
│                                 │ HTTP (JSON/NDJSON)                         │
│                                 ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    FastAPI Backend (Port 8888)                       │    │
│  │                                                                      │    │
│  │  • REST API endpoints                                                │    │
│  │  • Workflow visualization (n8n-demo)                                 │    │
│  │  • Streaming response support                                        │    │
│  └──────────────────────────────┬──────────────────────────────────────┘    │
│                                 │                                            │
│                                 ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                 Workflow Execution Engine (Python)                   │    │
│  │                                                                      │    │
│  │  ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐   │    │
│  │  │  Trigger  │ →  │  Agent 1  │ →  │  Agent 2  │ →  │  Output   │   │    │
│  │  │           │    │ (Analyze) │    │ (Report)  │    │ (File)    │   │    │
│  │  └───────────┘    └─────┬─────┘    └─────┬─────┘    └───────────┘   │    │
│  │                         │                │                          │    │
│  │                    ┌────┴────┐      ┌────┴────┐                     │    │
│  │                    │ Memory  │      │ Parser  │                     │    │
│  │                    │ Tools   │      │ LLM     │                     │    │
│  │                    │ LLM     │      └─────────┘                     │    │
│  │                    └─────────┘                                      │    │
│  └──────────────────────────────┬──────────────────────────────────────┘    │
│                                 │                                            │
│                                 ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      External Services                               │    │
│  │                                                                      │    │
│  │  • DeepSeek LLM API (OpenAI-compatible)                              │    │
│  │  • NUS News RSS Feed                                                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
project/
├── README.md                 # This file - project overview
├── environment.yml           # Conda environment configuration
├── start.sh                  # Start all services
├── stop.sh                   # Stop all services
│
├── chatbot/                  # Chainlit chat frontend
│   ├── README.md             # Frontend documentation
│   ├── app.py                # Main application
│   └── public/elements/      # Custom UI components
│
└── server/                   # FastAPI backend server
    ├── README.md             # Backend documentation
    ├── main.py               # API entry point
    ├── n8n_utils.py          # Workflow visualization
    ├── NUS News ChatBot.json # Workflow definition
    │
    └── workflow/             # Workflow execution engine
        ├── README.md         # Engine documentation
        ├── models.py         # Data models
        ├── workflow.py       # Workflow parser
        ├── context.py        # Execution context
        ├── executor.py       # Main executor
        └── nodes/            # Node executors
```

## Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Frontend | Chainlit | Chat UI framework |
| Backend | FastAPI | REST API server |
| Workflow | Custom Python | n8n-style workflow engine |
| LLM | DeepSeek API | AI language model |
| HTTP Client | httpx | Async HTTP requests |

## Installation

### Prerequisites

- [Miniconda](https://docs.conda.io/en/latest/miniconda.html) or [Anaconda](https://www.anaconda.com/)
- DeepSeek API key (get one at [DeepSeek Platform](https://platform.deepseek.com/))

### Setup

```bash
# 1. Create conda environment
conda env create -f environment.yml

# 2. Activate environment
conda activate cs4262-5462

# 3. Configure API key
echo "DEEPSEEK_API_KEY=your-api-key-here" > server/.env
```

### Environment Management

```bash
# Update environment (after modifying environment.yml)
conda env update -f environment.yml --prune

# Delete environment (if needed)
conda env remove -n cs4262-5462
```

## Quick Start

### Start Services

```bash
./start.sh
```

This script starts both services in the background:
- **Chatbot**: Chainlit UI on port 8000
- **Server**: FastAPI API on port 8888

Logs are saved to:
- `chatbot/chatbot.log`
- `server/server.log`

### Stop Services

```bash
./stop.sh
```

### Access the Application

| Service | URL |
|---------|-----|
| Chatbot UI | http://localhost:8000 |
| Server API | http://localhost:8888 |
| Health Check | http://localhost:8888/health |

## Usage

1. Open the Chatbot UI at http://localhost:8000
2. Select a command:
   - **get_workflow**: View the workflow visualization
   - **run_workflow**: Execute the workflow with your message
3. Type your message (e.g., "Show me NUS news from last week")
4. View the streaming results and generated report

## API Reference

### GET /health

Health check endpoint.

**Response:**
```json
{"status": "ok"}
```

### POST /get_workflow

Returns workflow visualization HTML.

**Response:**
```json
{
  "type": "message",
  "name": "Workflow Preview",
  "text": "Successfully built workflow: **NUS News ChatBot**",
  "html": "<!doctype html>..."
}
```

### POST /run_workflow

Executes workflow with streaming response.

**Request:**
```json
{
  "session_id": "user-123",
  "chat_history": [
    {"role": "user", "content": "Show me NUS news"}
  ],
  "files": []
}
```

**Response:** NDJSON stream
```
{"type":"step","name":"When chat message received","text":"..."}
{"type":"step","name":"Analyze Agent","text":"...","html":"..."}
{"type":"message","name":"NUS News ChatBot","text":"...","html":"..."}
```

## Manual Start (Alternative)

If you prefer to run services in foreground for debugging:

```bash
# Terminal 1: Start server
cd server
python main.py

# Terminal 2: Start chatbot
cd chatbot
chainlit run app.py --port 8000
```

## Key Concepts

### 1. Agentic Workflow

The system uses a workflow-based approach where:
- **Nodes** represent individual processing steps
- **Connections** define data flow between nodes
- **Agents** are special nodes that can use tools and make decisions

### 2. Streaming Responses

The backend uses NDJSON (Newline Delimited JSON) for real-time streaming:
- Each node completion sends a notification
- Frontend displays progress in real-time
- No waiting for entire workflow to complete

### 3. Session Management

Each user session maintains:
- Conversation history
- Memory buffer for context
- Uploaded files

## Extension Guide

### Adding New Features

| Task | Documentation |
|------|---------------|
| Add new chat commands | [chatbot/README.md](chatbot/README.md#adding-new-commands) |
| Add new API endpoints | [server/README.md](server/README.md#adding-new-api-endpoints) |
| Add new node types | [server/workflow/README.md](server/workflow/README.md#adding-a-new-node-type) |
| Add new LLM providers | [server/workflow/README.md](server/workflow/README.md#adding-a-new-ai-sub-node) |

### Creating Custom Workflows

1. Design your workflow in n8n format (JSON)
2. Add required node executors in `server/workflow/nodes/`
3. Register executors in `server/workflow/nodes/__init__.py`
4. Update the workflow JSON file path in `server/main.py`

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| Port already in use | Run `./stop.sh` or kill processes manually |
| API key error | Check `server/.env` file exists and contains valid key |
| Module not found | Run `conda activate cs4262-5462` |
| Connection refused | Ensure server is running on port 8888 |

### Checking Logs

```bash
# View server logs
tail -f server/server.log

# View chatbot logs
tail -f chatbot/chatbot.log
```

## Learning Resources

- [Chainlit Documentation](https://docs.chainlit.io)
- [FastAPI Documentation](https://fastapi.tiangolo.com)
- [n8n Documentation](https://docs.n8n.io)
- [OpenAI API Reference](https://platform.openai.com/docs/api-reference)
- [DeepSeek API Documentation](https://platform.deepseek.com/api-docs)

## License

This project is for educational purposes.

"""
Simple FastAPI server that serves n8n workflow preview and execution.

Endpoints:
    - POST /get_workflow: Returns HTML with n8n-demo component
    - POST /run_workflow: Execute the workflow with streaming NDJSON responses
"""

import logging
import os
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
import uvicorn

# Load environment variables — check backend/.env then project root .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv()

# Path to fallback workflow JSON
WORKFLOW_PATH = os.path.join(os.path.dirname(__file__), "..", "workflows", "example_shopping.json")

from backend.n8n_utils import build_n8n_demo_html
from backend.workflow_generator import generate_workflow
from workflow_engine import WorkflowExecutor, session_store

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

app = FastAPI(title="n8n Workflow Server")

# Enable CORS for chatbot integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8888")

# In-memory cache: session_id -> generated workflow HTML
_editor_cache: dict = {}


@app.post("/get_workflow")
async def get_workflow(payload: dict = Body(default={})):
    """Generate a workflow and return a link to the editable graph editor."""
    try:
        session_id = payload.get("session_id", "default")
        workflow = generate_workflow(payload)
        html = build_n8n_demo_html(workflow, backend_url=BACKEND_URL)
        _editor_cache[session_id] = html
        editor_url = f"{BACKEND_URL}/workflow_editor/{session_id}"
        return {
            "type": "message",
            "name": "Workflow Preview",
            "text": (
                f"Workflow **{workflow.get('name', 'Unknown')}** generated.\n\n"
                f"[Open Editor →]({editor_url})"
            ),
            "html": "",
        }
    except Exception as e:
        return {
            "type": "message",
            "name": "Error",
            "text": f"Unexpected error: {e}",
            "html": "",
        }


@app.get("/workflow_editor/{session_id}", response_class=HTMLResponse)
async def workflow_editor(session_id: str):
    """Serve the editable workflow graph editor for the given session."""
    html = _editor_cache.get(session_id)
    if not html:
        return HTMLResponse("<h2>No workflow found for this session. Run /get_workflow first.</h2>", status_code=404)
    return HTMLResponse(html)


logger = logging.getLogger(__name__)


@app.post("/run_workflow")
async def run_workflow(payload: dict = Body(default={})):
    """Execute a workflow and stream NDJSON results.

    If payload contains a 'workflow' key, that workflow JSON is used directly
    (e.g. submitted from the editable graph editor). Otherwise a new workflow
    is generated from the user query via the SFT/DeepSeek/fallback chain.
    """
    session_id = payload.get("session_id", "default")
    chat_history = payload.get("chat_history", [])
    files = payload.get("files", [])

    logger.info(f"[run_workflow] session_id={session_id}, files={len(files)}")

    if "workflow" in payload and payload["workflow"]:
        workflow = payload["workflow"]
        logger.info("[run_workflow] using pre-built workflow from payload")
    else:
        workflow = generate_workflow(payload)
    executor = WorkflowExecutor.from_json(workflow)

    async def stream():
        async for n in executor.execute(session_id, chat_history, files):
            yield n.to_json()

    return StreamingResponse(
        stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/sessions")
async def list_sessions():
    """List all active sessions with metadata (multi-tenancy observability)."""
    session_store.evict_stale(max_age_seconds=3600)
    return {"sessions": session_store.active_sessions()}


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Evict a specific session from the store."""
    session_store.delete(session_id)
    return {"deleted": session_id}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8888)

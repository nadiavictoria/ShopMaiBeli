"""
Simple FastAPI server that serves n8n workflow preview and execution.

Endpoints:
    - POST /get_workflow: Returns HTML with n8n-demo component
    - POST /run_workflow: Execute the workflow with streaming NDJSON responses
"""

import json
import logging
import os
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import uvicorn

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Path to workflow JSON (relative to project root, one level up from backend/)
WORKFLOW_PATH = os.path.join(os.path.dirname(__file__), "..", "workflows", "example_shopping.json")

from backend.n8n_utils import build_n8n_demo_html
from workflow_engine import WorkflowExecutor

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


def generate_workflow(payload: dict) -> dict:
    """
    Load the example shopping workflow JSON.

    In Point 3 (Workflow Generation), this will be replaced with a function that
    calls a generative model (Claude API or fine-tuned SFT model) to create
    workflow JSON based on user queries.

    For now, returns a hardcoded example workflow.
    """
    _ = payload  # Reserved for future use (will contain chat history, etc.)
    with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@app.post("/get_workflow")
async def get_workflow(payload: dict = Body(default={})):
    """
    Return HTML with n8n-demo visualization of the n8n workflow.
    """
    try:
        workflow = generate_workflow(payload)
        html = build_n8n_demo_html(workflow)
        return {
            "type": "message",
            "name": "Workflow Preview",
            "text": f"Successfully built workflow: **{workflow.get('name', 'Unknown')}**",
            "html": html,
        }
    except Exception as e:
        return {
            "type": "message",
            "name": "Error",
            "text": f"Unexpected error: {e}",
            "html": "",
        }


# Global workflow executor instance (lazy loaded)
_workflow_executor = None


def get_workflow_executor() -> WorkflowExecutor:
    """Get or create the workflow executor instance."""
    global _workflow_executor
    if _workflow_executor is None:
        _workflow_executor = WorkflowExecutor.from_file(WORKFLOW_PATH)
    return _workflow_executor


logger = logging.getLogger(__name__)


@app.post("/run_workflow")
async def run_workflow(payload: dict = Body(default={})):
    """Run the workflow and stream results as NDJSON."""
    session_id = payload.get("session_id", "default")
    chat_history = payload.get("chat_history", [])
    files = payload.get("files", [])

    logger.info(f"[run_workflow] session_id={session_id}, files={len(files)}")

    async def stream():
        async for n in get_workflow_executor().execute(session_id, chat_history, files):
            yield n.to_json()

    return StreamingResponse(
        stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8888)

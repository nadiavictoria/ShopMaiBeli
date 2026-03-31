import json
import logging
import os
import sys

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

# Add project root to path so workflow_engine and nodes are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workflow_engine import WorkflowExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="ShopMaiBeli Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class WorkflowRequest(BaseModel):
    chat_history: list[dict] = []
    session_id: str = "default"


class RunWorkflowRequest(BaseModel):
    session_id: str = "default"
    chat_history: list[dict] = []
    files: list = []


def extract_query(chat_history: list[dict]) -> str:
    for msg in reversed(chat_history):
        if msg.get("role") == "user":
            return msg.get("content", "")
    return ""


def validate_workflow(workflow: dict) -> list[str]:
    errors = []
    for key in ("name", "nodes", "connections"):
        if key not in workflow:
            errors.append(f"Missing '{key}'")
    if "nodes" not in workflow:
        return errors

    node_names = {n["name"] for n in workflow["nodes"]}
    node_types = [n.get("type", "").split(".")[-1] for n in workflow["nodes"]]

    if "chatTrigger" not in node_types:
        errors.append("No chatTrigger node")
    if "convertToFile" not in node_types:
        errors.append("No convertToFile node")

    for source, conns in workflow.get("connections", {}).items():
        if source not in node_names:
            errors.append(f"Connection source '{source}' not in nodes")
        if isinstance(conns, dict):
            for conn_type, outputs in conns.items():
                for output_list in outputs:
                    for conn in output_list:
                        if isinstance(conn, dict) and conn.get("node") not in node_names:
                            errors.append(f"Connection target '{conn.get('node')}' not in nodes")
    return errors


def load_example_workflow() -> dict:
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workflows", "example_shopping.json")
    with open(path) as f:
        return json.load(f)


def generate_workflow(payload: dict) -> dict:
    chat_history = payload.get("chat_history", [])
    user_query = extract_query(chat_history)
    api_key = os.getenv("DEEPSEEK_API_KEY", "")

    if user_query and api_key:
        try:
            import httpx
            prompt_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "models", "prompts", "workflow_gen.txt"
            )
            with open(prompt_path) as f:
                system_prompt = f.read()

            resp = httpx.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"User wants to: {user_query}"}
                    ],
                    "max_tokens": 4096
                },
                timeout=30
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]

            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                workflow = json.loads(content[start:end])
                if not validate_workflow(workflow):
                    return workflow
        except Exception as e:
            logger.warning(f"LLM workflow generation failed: {e} — falling back to example workflow")

    return load_example_workflow()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/get_workflow")
async def get_workflow(request: WorkflowRequest):
    try:
        workflow = generate_workflow({"chat_history": request.chat_history})
        return workflow
    except Exception as e:
        logger.error(f"get_workflow error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/run_workflow")
async def run_workflow(request: RunWorkflowRequest):
    try:
        workflow = generate_workflow({"chat_history": request.chat_history})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow generation failed: {e}")

    executor = WorkflowExecutor.from_json(workflow)

    async def stream_events():
        try:
            async for notification in executor.execute(
                session_id=request.session_id,
                chat_history=request.chat_history,
                files=request.files
            ):
                if notification.notification_type == "start":
                    event = {
                        "type": "node_started",
                        "node_name": notification.node_name,
                    }
                elif notification.notification_type == "message":
                    event = {
                        "type": "final",
                        "node_name": notification.node_name,
                        "message": notification.message,
                        "html": notification.data.get("html", ""),
                        "data": notification.data
                    }
                else:
                    event = {
                        "type": "node_completed",
                        "node_name": notification.node_name,
                        "message": notification.message,
                        "data": notification.data
                    }
                yield json.dumps(event) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

    return StreamingResponse(stream_events(), media_type="application/x-ndjson")

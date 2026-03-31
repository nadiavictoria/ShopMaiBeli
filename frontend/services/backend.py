"""HTTP client for the real FastAPI backend."""
import os
import json
import httpx

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8888")


async def get_workflow(chat_history: list[dict]) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BACKEND_URL}/get_workflow",
            json={"chat_history": chat_history}
        )
        resp.raise_for_status()
        return resp.json()


async def run_workflow(session_id: str, chat_history: list[dict]):
    """Stream NDJSON events from /run_workflow."""
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST",
            f"{BACKEND_URL}/run_workflow",
            json={"session_id": session_id, "chat_history": chat_history, "files": []}
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if line:
                    yield json.loads(line)


def n8n_connections_to_simple(connections: dict) -> dict:
    """Convert n8n connection format to simplified {NodeA: [NodeB, ...]} format for WorkflowGraph."""
    simple = {}
    for source, conn_types in connections.items():
        targets = []
        if isinstance(conn_types, dict):
            for conn_type, outputs in conn_types.items():
                if conn_type == "main":
                    for output_list in outputs:
                        for conn in output_list:
                            if isinstance(conn, dict) and "node" in conn:
                                targets.append(conn["node"])
        elif isinstance(conn_types, list):
            targets = conn_types
        simple[source] = targets
    return simple


def workflow_for_display(workflow: dict) -> dict:
    """Convert a full n8n workflow JSON to the simplified format WorkflowGraph expects."""
    # Filter out AI sub-nodes (only show main-flow nodes)
    main_types = {"chatTrigger", "agent", "productSearch", "reviewAnalyzer", "convertToFile"}
    
    nodes = []
    for node in workflow.get("nodes", []):
        node_type = node.get("type", "").split(".")[-1]
        if node_type in main_types or node_type not in {
            "lmChatDeepSeek", "memoryBufferWindow", "outputParserStructured", "toolCode"
        }:
            nodes.append({
                "name": node["name"],
                "type": _display_type(node_type)
            })
    
    connections = n8n_connections_to_simple(workflow.get("connections", {}))
    
    return {"nodes": nodes, "connections": connections}


def _display_type(node_type: str) -> str:
    mapping = {
        "chatTrigger": "trigger",
        "agent": "agent",
        "productSearch": "api",
        "reviewAnalyzer": "rag",
        "convertToFile": "output",
    }
    return mapping.get(node_type, node_type)

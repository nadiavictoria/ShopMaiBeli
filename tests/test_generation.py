"""
Workflow generation / validation tests.

Validates that workflow JSON files are structurally correct.
Also tests the validate_workflow() utility used by the generation pipeline.
Run with:  pytest tests/test_generation.py -v
"""

import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from workflow_engine import WorkflowExecutor
from workflow_engine.workflow import Workflow


# ---------------------------------------------------------------------------
# Validation utility
# ---------------------------------------------------------------------------

def validate_workflow(workflow: dict) -> list:
    """
    Validate a workflow dict for structural correctness.

    Returns a list of error strings (empty list means valid).

    Rules checked
    ~~~~~~~~~~~~~
    1. Must have 'name'
    2. Must have 'nodes' list
    3. Must have 'connections' dict
    4. Must have at least one chatTrigger-type node
    5. All connection sources and targets must reference valid node names
    6. Every node must have 'id', 'name', 'type', 'typeVersion', 'position'
    """
    errors = []

    if "name" not in workflow:
        errors.append("Missing 'name'")

    if "nodes" not in workflow:
        errors.append("Missing 'nodes'")
        return errors  # can't continue without nodes

    if not isinstance(workflow["nodes"], list):
        errors.append("'nodes' must be a list")
        return errors

    if "connections" not in workflow:
        errors.append("Missing 'connections'")

    # Build node name set and check per-node required fields
    node_names = set()
    for i, node in enumerate(workflow["nodes"]):
        for required in ("id", "name", "type", "typeVersion", "position"):
            if required not in node:
                errors.append(f"Node[{i}] missing required field '{required}'")
        if "name" in node:
            node_names.add(node["name"])

    # Must have a trigger node
    node_types = [
        n.get("type", "").split(".")[-1]
        for n in workflow.get("nodes", [])
    ]
    if "chatTrigger" not in node_types:
        errors.append("No chatTrigger node found")

    # Validate connection references
    for source, conns in workflow.get("connections", {}).items():
        if source not in node_names:
            errors.append(
                f"Connection source '{source}' does not match any node name"
            )
        if not isinstance(conns, dict):
            errors.append(f"Connections for '{source}' must be a dict")
            continue
        for conn_type, outputs in conns.items():
            if not isinstance(outputs, list):
                errors.append(
                    f"Connection '{source}.{conn_type}' outputs must be a list"
                )
                continue
            for output_list in outputs:
                if not isinstance(output_list, list):
                    errors.append(
                        f"Connection '{source}.{conn_type}' inner list must be a list"
                    )
                    continue
                for conn in output_list:
                    if "node" not in conn:
                        errors.append(
                            f"Connection in '{source}.{conn_type}' missing 'node' key"
                        )
                    elif conn["node"] not in node_names:
                        errors.append(
                            f"Connection target '{conn['node']}' does not match any node name"
                        )

    return errors


# ---------------------------------------------------------------------------
# Tests for validate_workflow utility itself
# ---------------------------------------------------------------------------

def test_validate_accepts_minimal_valid():
    """A minimal trigger-only workflow is valid."""
    wf = {
        "name": "Test",
        "nodes": [
            {"id": "1", "name": "Trigger", "type": "chatTrigger",
             "typeVersion": 1.4, "position": [0, 0], "parameters": {}}
        ],
        "connections": {}
    }
    errors = validate_workflow(wf)
    assert errors == [], f"Unexpected errors: {errors}"


def test_validate_rejects_missing_name():
    wf = {
        "nodes": [
            {"id": "1", "name": "Trigger", "type": "chatTrigger",
             "typeVersion": 1.4, "position": [0, 0]}
        ],
        "connections": {}
    }
    errors = validate_workflow(wf)
    assert any("name" in e.lower() for e in errors)


def test_validate_rejects_missing_nodes():
    wf = {"name": "No Nodes", "connections": {}}
    errors = validate_workflow(wf)
    assert any("nodes" in e.lower() for e in errors)


def test_validate_rejects_missing_trigger():
    wf = {
        "name": "No Trigger",
        "nodes": [
            {"id": "1", "name": "Search", "type": "productSearch",
             "typeVersion": 1.0, "position": [0, 0]}
        ],
        "connections": {}
    }
    errors = validate_workflow(wf)
    assert any("trigger" in e.lower() for e in errors)


def test_validate_rejects_bad_connection_source():
    wf = {
        "name": "Bad Source",
        "nodes": [
            {"id": "1", "name": "Trigger", "type": "chatTrigger",
             "typeVersion": 1.4, "position": [0, 0]}
        ],
        "connections": {
            "NonExistentNode": {"main": [[{"node": "Trigger", "type": "main", "index": 0}]]}
        }
    }
    errors = validate_workflow(wf)
    assert any("source" in e.lower() or "NonExistentNode" in e for e in errors)


def test_validate_rejects_bad_connection_target():
    wf = {
        "name": "Bad Target",
        "nodes": [
            {"id": "1", "name": "Trigger", "type": "chatTrigger",
             "typeVersion": 1.4, "position": [0, 0]}
        ],
        "connections": {
            "Trigger": {"main": [[{"node": "Ghost", "type": "main", "index": 0}]]}
        }
    }
    errors = validate_workflow(wf)
    assert any("Ghost" in e for e in errors)


def test_validate_multi_node_workflow():
    """Full Trigger → Search → Reviews chain should be valid."""
    wf = {
        "name": "Full Chain",
        "nodes": [
            {"id": "1", "name": "Trigger", "type": "chatTrigger",
             "typeVersion": 1.4, "position": [0, 0]},
            {"id": "2", "name": "Search", "type": "productSearch",
             "typeVersion": 1.0, "position": [240, 0]},
            {"id": "3", "name": "Reviews", "type": "reviewAnalyzer",
             "typeVersion": 1.0, "position": [480, 0]},
        ],
        "connections": {
            "Trigger": {"main": [[{"node": "Search", "type": "main", "index": 0}]]},
            "Search":  {"main": [[{"node": "Reviews", "type": "main", "index": 0}]]},
        }
    }
    errors = validate_workflow(wf)
    assert errors == [], f"Unexpected errors: {errors}"


# ---------------------------------------------------------------------------
# Workflow round-trip: parse, execute, validate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workflow_round_trip():
    """A hand-crafted workflow JSON survives parse → execute → no exceptions."""
    wf_json = {
        "name": "Round Trip",
        "nodes": [
            {"id": "1", "name": "Trigger", "type": "chatTrigger",
             "typeVersion": 1.4, "position": [0, 0], "parameters": {}},
            {"id": "2", "name": "Search", "type": "productSearch",
             "typeVersion": 1.0, "position": [240, 0],
             "parameters": {"source": "mock", "maxResults": 2}},
        ],
        "connections": {
            "Trigger": {"main": [[{"node": "Search", "type": "main", "index": 0}]]},
        }
    }
    # Must be structurally valid
    assert validate_workflow(wf_json) == []

    # Must parse and execute without error
    executor = WorkflowExecutor.from_json(wf_json)
    notifs = []
    async for n in executor.execute(
        session_id="round-trip",
        chat_history=[{"role": "user", "content": "headphones"}]
    ):
        notifs.append(n)

    assert notifs[-1].notification_type == "message"
    assert "successfully" in notifs[-1].message.lower()


@pytest.mark.asyncio
async def test_workflow_topological_order():
    """Execution order must respect dependencies: Trigger before Search before Reviews."""
    wf_json = {
        "name": "Order Test",
        "nodes": [
            {"id": "1", "name": "Trigger", "type": "chatTrigger",
             "typeVersion": 1.4, "position": [0, 0], "parameters": {}},
            {"id": "2", "name": "Search", "type": "productSearch",
             "typeVersion": 1.0, "position": [240, 0],
             "parameters": {"source": "mock"}},
            {"id": "3", "name": "Reviews", "type": "reviewAnalyzer",
             "typeVersion": 1.0, "position": [480, 0], "parameters": {}},
        ],
        "connections": {
            "Trigger": {"main": [[{"node": "Search",  "type": "main", "index": 0}]]},
            "Search":  {"main": [[{"node": "Reviews", "type": "main", "index": 0}]]},
        }
    }
    workflow = Workflow(wf_json)
    order = workflow.get_execution_order()

    assert order.index("Trigger") < order.index("Search")
    assert order.index("Search") < order.index("Reviews")


# ---------------------------------------------------------------------------
# On-disk example workflow (STEP 7)
# ---------------------------------------------------------------------------

def _workflow_path(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), "..", "workflows", filename)


def test_example_shopping_workflow_valid():
    """workflows/example_shopping.json must pass structural validation."""
    path = _workflow_path("example_shopping.json")
    if not os.path.exists(path):
        pytest.skip("example_shopping.json not yet created (STEP 7)")

    with open(path) as f:
        wf = json.load(f)

    errors = validate_workflow(wf)
    assert errors == [], f"Validation errors in example_shopping.json: {errors}"


def test_example_shopping_workflow_parseable():
    """workflows/example_shopping.json must be parseable by WorkflowExecutor."""
    path = _workflow_path("example_shopping.json")
    if not os.path.exists(path):
        pytest.skip("example_shopping.json not yet created (STEP 7)")

    executor = WorkflowExecutor.from_file(path)
    order = executor.workflow.get_execution_order()
    assert len(order) >= 2, "Expected at least Trigger + one other node"


def test_with_reviews_workflow_valid():
    """workflows/with_reviews.json must pass structural validation."""
    path = _workflow_path("with_reviews.json")
    if not os.path.exists(path):
        pytest.skip("with_reviews.json not yet created (STEP 7)")

    with open(path) as f:
        wf = json.load(f)

    errors = validate_workflow(wf)
    assert errors == [], f"Validation errors in with_reviews.json: {errors}"

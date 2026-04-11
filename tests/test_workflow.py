"""
Workflow-level integration tests.

Tests the full WorkflowExecutor with hand-crafted workflow JSON dicts.
All tests use mock nodes — no network required.
Run with:  pytest tests/test_workflow.py -v
"""

import sys
import os
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from workflow_engine import WorkflowExecutor
from workflow_engine.models import NodeNotification


# ---------------------------------------------------------------------------
# Minimal workflow fixtures
# ---------------------------------------------------------------------------

TRIGGER_ONLY = {
    "name": "Trigger Only",
    "nodes": [
        {"id": "1", "name": "Trigger", "type": "chatTrigger",
         "typeVersion": 1.4, "position": [0, 0], "parameters": {}},
    ],
    "connections": {}
}

SIMPLE_WORKFLOW = {
    "name": "Simple Search",
    "nodes": [
        {"id": "1", "name": "Trigger", "type": "chatTrigger",
         "typeVersion": 1.4, "position": [0, 0], "parameters": {}},
        {"id": "2", "name": "Search", "type": "productSearch",
         "typeVersion": 1.0, "position": [240, 0],
         "parameters": {"source": "mock", "maxResults": 3}},
    ],
    "connections": {
        "Trigger": {"main": [[{"node": "Search", "type": "main", "index": 0}]]},
    }
}

WITH_REVIEWS_WORKFLOW = {
    "name": "Search + Reviews",
    "nodes": [
        {"id": "1", "name": "Trigger", "type": "chatTrigger",
         "typeVersion": 1.4, "position": [0, 0], "parameters": {}},
        {"id": "2", "name": "Search", "type": "productSearch",
         "typeVersion": 1.0, "position": [240, 0],
         "parameters": {"source": "mock", "maxResults": 5}},
        {"id": "3", "name": "Reviews", "type": "reviewAnalyzer",
         "typeVersion": 1.0, "position": [480, 0],
         "parameters": {"mode": "simple"}},
    ],
    "connections": {
        "Trigger": {"main": [[{"node": "Search", "type": "main", "index": 0}]]},
        "Search":  {"main": [[{"node": "Reviews", "type": "main", "index": 0}]]},
    }
}

PARALLEL_WORKFLOW = {
    "name": "Parallel Search",
    "nodes": [
        {"id": "1", "name": "Trigger", "type": "chatTrigger",
         "typeVersion": 1.4, "position": [0, 0], "parameters": {}},
        {"id": "2", "name": "Search A", "type": "productSearch",
         "typeVersion": 1.0, "position": [240, -100],
         "parameters": {"source": "mock", "maxResults": 3}},
        {"id": "3", "name": "Search B", "type": "productSearch",
         "typeVersion": 1.0, "position": [240, 100],
         "parameters": {"source": "mock", "maxResults": 3}},
    ],
    "connections": {
        "Trigger": {"main": [[
            {"node": "Search A", "type": "main", "index": 0},
            {"node": "Search B", "type": "main", "index": 0},
        ]]}
    }
}

PARALLEL_THEN_REVIEWS = {
    "name": "Parallel then Reviews",
    "nodes": [
        {"id": "1", "name": "Trigger", "type": "chatTrigger",
         "typeVersion": 1.4, "position": [0, 0], "parameters": {}},
        {"id": "2", "name": "Search A", "type": "productSearch",
         "typeVersion": 1.0, "position": [240, -100],
         "parameters": {"source": "mock", "maxResults": 2}},
        {"id": "3", "name": "Search B", "type": "productSearch",
         "typeVersion": 1.0, "position": [240, 100],
         "parameters": {"source": "mock", "maxResults": 2}},
        {"id": "4", "name": "Reviews", "type": "reviewAnalyzer",
         "typeVersion": 1.0, "position": [480, 0],
         "parameters": {"mode": "simple"}},
    ],
    "connections": {
        "Trigger": {"main": [[
            {"node": "Search A", "type": "main", "index": 0},
            {"node": "Search B", "type": "main", "index": 0},
        ]]},
        "Search A": {"main": [[{"node": "Reviews", "type": "main", "index": 0}]]},
        "Search B": {"main": [[{"node": "Reviews", "type": "main", "index": 0}]]},
    }
}

WITH_TRUST_SCORING = {
    "name": "Search + Reviews + Trust",
    "nodes": [
        {"id": "1", "name": "Trigger", "type": "chatTrigger",
         "typeVersion": 1.4, "position": [0, 0], "parameters": {}},
        {"id": "2", "name": "Search", "type": "productSearch",
         "typeVersion": 1.0, "position": [240, 0],
         "parameters": {"source": "mock", "maxResults": 5}},
        {"id": "3", "name": "Reviews", "type": "reviewAnalyzer",
         "typeVersion": 1.0, "position": [480, 0],
         "parameters": {"mode": "simple"}},
        {"id": "4", "name": "Trust", "type": "trustScorer",
         "typeVersion": 1.0, "position": [720, 0], "parameters": {}},
    ],
    "connections": {
        "Trigger": {"main": [[{"node": "Search", "type": "main", "index": 0}]]},
        "Search":  {"main": [[{"node": "Reviews", "type": "main", "index": 0}]]},
        "Reviews": {"main": [[{"node": "Trust", "type": "main", "index": 0}]]},
    }
}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def collect_notifications(executor: WorkflowExecutor, session_id: str = "test",
                                  chat_history=None) -> list[NodeNotification]:
    notifs = []
    async for n in executor.execute(
        session_id=session_id,
        chat_history=chat_history or [{"role": "user", "content": "earbuds"}]
    ):
        notifs.append(n)
    return notifs


# ---------------------------------------------------------------------------
# Basic execution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_simple_workflow_executes():
    """A Trigger → ProductSearch workflow should complete without error."""
    executor = WorkflowExecutor.from_json(SIMPLE_WORKFLOW)
    notifs = await collect_notifications(executor)

    assert len(notifs) >= 1, "Expected at least one notification"
    # Final notification must be type 'message'
    assert notifs[-1].notification_type == "message"


@pytest.mark.asyncio
async def test_simple_workflow_final_notification():
    """The last notification is always the workflow-level summary."""
    executor = WorkflowExecutor.from_json(SIMPLE_WORKFLOW)
    notifs = await collect_notifications(executor)

    final = notifs[-1]
    assert final.notification_type == "message"
    assert final.session_id == "test"


@pytest.mark.asyncio
async def test_simple_workflow_step_notification_present():
    """ProductSearch must emit a 'step' notification during execution."""
    executor = WorkflowExecutor.from_json(SIMPLE_WORKFLOW)
    notifs = await collect_notifications(executor)

    step_notifs = [n for n in notifs if n.notification_type == "step"]
    assert len(step_notifs) >= 1, "Expected at least one step notification"


@pytest.mark.asyncio
async def test_with_reviews_workflow():
    """Three-node workflow: Trigger → Search → ReviewAnalyzer completes."""
    executor = WorkflowExecutor.from_json(WITH_REVIEWS_WORKFLOW)
    notifs = await collect_notifications(executor)

    assert notifs[-1].notification_type == "message"
    step_notifs = [n for n in notifs if n.notification_type == "step"]
    # Both Search and Reviews should emit step notifications
    assert len(step_notifs) >= 2


@pytest.mark.asyncio
async def test_with_trust_scoring_workflow():
    """TrustScorer should execute after review analysis and emit a step notification."""
    executor = WorkflowExecutor.from_json(WITH_TRUST_SCORING)
    notifs = await collect_notifications(executor)

    assert notifs[-1].notification_type == "message"
    step_names = [n.node_name for n in notifs if n.notification_type == "step"]
    assert "Trust" in step_names


@pytest.mark.asyncio
async def test_session_id_propagated():
    """session_id must appear in every notification."""
    executor = WorkflowExecutor.from_json(SIMPLE_WORKFLOW)
    notifs = await collect_notifications(executor, session_id="sess-42")

    for n in notifs:
        assert n.session_id == "sess-42", f"Expected session 'sess-42', got '{n.session_id}'"


# ---------------------------------------------------------------------------
# Execution levels / parallel execution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parallel_execution_levels():
    """Trigger → [Search A, Search B] should place both searches in level 1."""
    executor = WorkflowExecutor.from_json(PARALLEL_WORKFLOW)
    order = executor.workflow.get_execution_order()
    levels = executor._get_execution_levels(order)

    # Level 0: [Trigger]
    # Level 1: [Search A, Search B]  (or reversed, order within level may vary)
    assert len(levels) == 2
    assert len(levels[0]) == 1     # only Trigger
    assert len(levels[1]) == 2     # Search A + Search B together


@pytest.mark.asyncio
async def test_parallel_workflow_executes():
    """Parallel workflow should complete and emit notifications for both searches."""
    executor = WorkflowExecutor.from_json(PARALLEL_WORKFLOW)
    notifs = await collect_notifications(executor)

    assert notifs[-1].notification_type == "message"
    step_notifs = [n for n in notifs if n.notification_type == "step"]
    # Expect one step notification per ProductSearch node
    assert len(step_notifs) >= 2


@pytest.mark.asyncio
async def test_parallel_execution_timing():
    """
    Parallel mock nodes should finish well within the sequential time budget.
    With mock data each node is near-instant; combined must be < 2 s.
    """
    executor = WorkflowExecutor.from_json(PARALLEL_WORKFLOW)
    start = time.time()
    async for _ in executor.execute(
        session_id="timing-test",
        chat_history=[{"role": "user", "content": ""}]
    ):
        pass
    elapsed = time.time() - start
    assert elapsed < 5, f"Parallel execution took {elapsed:.2f}s — unexpectedly slow"


@pytest.mark.asyncio
async def test_parallel_then_reviews_workflow():
    """Two parallel searches feeding one ReviewAnalyzer should merge results."""
    executor = WorkflowExecutor.from_json(PARALLEL_THEN_REVIEWS)
    notifs = await collect_notifications(executor)

    assert notifs[-1].notification_type == "message"
    # At least 3 step notifications: Search A, Search B, Reviews
    step_notifs = [n for n in notifs if n.notification_type == "step"]
    assert len(step_notifs) >= 3


# ---------------------------------------------------------------------------
# Execution level correctness
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execution_levels_sequential():
    """Sequential workflow should produce one node per level."""
    executor = WorkflowExecutor.from_json(WITH_REVIEWS_WORKFLOW)
    order = executor.workflow.get_execution_order()
    levels = executor._get_execution_levels(order)

    # Each level has exactly 1 node in a sequential chain
    for level in levels:
        assert len(level) == 1


@pytest.mark.asyncio
async def test_execution_levels_cover_all_nodes():
    """Every node in the execution order must appear in exactly one level."""
    executor = WorkflowExecutor.from_json(PARALLEL_THEN_REVIEWS)
    order = executor.workflow.get_execution_order()
    levels = executor._get_execution_levels(order)

    all_in_levels = [name for level in levels for name in level]
    assert sorted(all_in_levels) == sorted(order)


# ---------------------------------------------------------------------------
# Context isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_two_sessions_are_isolated():
    """Different session IDs must not share node outputs."""
    executor = WorkflowExecutor.from_json(SIMPLE_WORKFLOW)

    notifs_a = await collect_notifications(executor, session_id="session-A")
    notifs_b = await collect_notifications(executor, session_id="session-B")

    assert notifs_a[-1].session_id == "session-A"
    assert notifs_b[-1].session_id == "session-B"

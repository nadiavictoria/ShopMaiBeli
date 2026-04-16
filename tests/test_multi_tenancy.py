"""
Multi-tenancy tests: verify concurrent workflow executions are fully isolated.

Tests prove:
1. Two users running the same workflow simultaneously do not share context state.
2. Per-session memory persists across sequential requests for the same user.
3. Concurrent same-session requests are serialized (no race conditions).
4. SessionStore eviction removes stale sessions.
"""

import asyncio
import pytest

from workflow_engine import WorkflowExecutor, session_store
from workflow_engine.session_store import SessionStore


SIMPLE_WORKFLOW = {
    "id": "test-wf",
    "name": "Test Workflow",
    "nodes": [
        {
            "id": "n1",
            "name": "Trigger",
            "type": "chatTrigger",
            "typeVersion": 1,
            "position": [0, 0],
            "parameters": {},
        }
    ],
    "connections": {},
    "settings": {},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _run(session_id: str, chat_history=None) -> list:
    """Run the simple workflow and collect all notifications."""
    executor = WorkflowExecutor.from_json(SIMPLE_WORKFLOW)
    notifications = []
    async for n in executor.execute(session_id, chat_history or []):
        notifications.append(n)
    return notifications


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_different_sessions_are_isolated():
    """
    Two users run workflows concurrently.
    Their contexts must not bleed into each other.
    """
    store = SessionStore()

    async def run_and_tag(session_id, tag):
        ctx = await store.get_or_create(session_id)
        ctx.memory[tag] = [{"role": "user", "content": f"Hello from {tag}"}]
        await asyncio.sleep(0.05)  # simulate work
        return ctx.memory

    results = await asyncio.gather(
        run_and_tag("user-alice", "alice"),
        run_and_tag("user-bob", "bob"),
    )

    alice_memory, bob_memory = results
    assert "alice" in alice_memory
    assert "bob" not in alice_memory

    assert "bob" in bob_memory
    assert "alice" not in bob_memory


@pytest.mark.asyncio
async def test_session_memory_persists_across_requests():
    """
    Sequential requests from the same session share persistent memory.
    """
    store = SessionStore()
    session_id = "persistent-user"

    ctx1 = await store.get_or_create(session_id)
    ctx1.memory["history"] = [{"role": "user", "content": "first message"}]

    # Simulate a second request — should get same context
    ctx2 = await store.get_or_create(session_id)
    assert ctx2.memory["history"][0]["content"] == "first message"
    assert ctx1 is ctx2  # same object


@pytest.mark.asyncio
async def test_concurrent_same_session_is_serialized():
    """
    Two concurrent requests for the same session must be serialized.
    The second request should only start after the first completes.
    """
    store = SessionStore()
    session_id = "serial-user"
    order = []

    async def task(label, delay):
        async with store.session_lock(session_id):
            order.append(f"{label}-start")
            await asyncio.sleep(delay)
            order.append(f"{label}-end")

    await asyncio.gather(task("A", 0.1), task("B", 0.05))

    # One task must complete entirely before the other starts
    assert order.index("A-end") < order.index("B-start") or \
           order.index("B-end") < order.index("A-start"), \
           f"Interleaved execution detected: {order}"


@pytest.mark.asyncio
async def test_different_sessions_run_in_parallel():
    """
    Different sessions should NOT block each other — they acquire different locks.
    """
    store = SessionStore()
    timeline = []

    async def task(session_id, label, delay):
        async with store.session_lock(session_id):
            timeline.append(f"{label}-start")
            await asyncio.sleep(delay)
            timeline.append(f"{label}-end")

    start = asyncio.get_event_loop().time()
    await asyncio.gather(
        task("session-x", "X", 0.1),
        task("session-y", "Y", 0.1),
    )
    elapsed = asyncio.get_event_loop().time() - start

    # If truly parallel, total time should be ~0.1s, not ~0.2s
    assert elapsed < 0.18, f"Sessions blocked each other (took {elapsed:.2f}s)"
    assert "X-start" in timeline and "Y-start" in timeline


@pytest.mark.asyncio
async def test_session_eviction():
    """Stale sessions are removed by evict_stale()."""
    import time
    store = SessionStore()

    await store.get_or_create("stale-session")
    # Manually backdate last_used
    store._sessions["stale-session"].last_used = time.time() - 7200  # 2 hours ago

    evicted = store.evict_stale(max_age_seconds=3600)
    assert "stale-session" in evicted
    assert store.get("stale-session") is None


@pytest.mark.asyncio
async def test_workflow_execution_concurrent_users():
    """
    Run the simple workflow for two different users concurrently.
    Both should complete successfully without errors.
    """
    # Clean up any leftover sessions from other tests
    session_store.delete("concurrent-user-1")
    session_store.delete("concurrent-user-2")

    results = await asyncio.gather(
        _run("concurrent-user-1", [{"role": "user", "content": "find earbuds"}]),
        _run("concurrent-user-2", [{"role": "user", "content": "find headphones"}]),
    )

    notifications_1, notifications_2 = results

    # Both should have produced at least a final notification
    assert len(notifications_1) >= 1
    assert len(notifications_2) >= 1

    # Sessions should be tracked in the global store
    sessions = session_store.active_sessions()
    assert "concurrent-user-1" in sessions
    assert "concurrent-user-2" in sessions

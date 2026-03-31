"""Tests for workflow execution engine."""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch

from workflow_engine.workflow import Workflow
from workflow_engine.executor import WorkflowExecutor
from workflow_engine.models import NodeNotification


SIMPLE_WORKFLOW = {
    "name": "Test Workflow",
    "nodes": [
        {"id": "1", "name": "Chat Trigger", "type": "@n8n/n8n-nodes-langchain.chatTrigger", "typeVersion": 1.4, "position": [0, 200], "parameters": {}},
        {"id": "2", "name": "ProductSearch", "type": "shopmaibeli.productSearch", "typeVersion": 1.0, "position": [220, 200], "parameters": {"source": "mock"}},
        {"id": "3", "name": "Convert to File", "type": "n8n-nodes-base.convertToFile", "typeVersion": 1.1, "position": [440, 200], "parameters": {"sourceProperty": "products", "options": {"fileName": "out.html"}}},
    ],
    "connections": {
        "Chat Trigger": {"main": [[{"node": "ProductSearch", "type": "main", "index": 0}]]},
        "ProductSearch": {"main": [[{"node": "Convert to File", "type": "main", "index": 0}]]},
    }
}

PARALLEL_WORKFLOW = {
    "name": "Parallel Test Workflow",
    "nodes": [
        {"id": "1", "name": "Chat Trigger", "type": "@n8n/n8n-nodes-langchain.chatTrigger", "typeVersion": 1.4, "position": [0, 200], "parameters": {}},
        {"id": "2", "name": "ProductSearch1", "type": "shopmaibeli.productSearch", "typeVersion": 1.0, "position": [220, 100], "parameters": {"source": "mock"}},
        {"id": "3", "name": "ProductSearch2", "type": "shopmaibeli.productSearch", "typeVersion": 1.0, "position": [220, 300], "parameters": {"source": "mock"}},
        {"id": "4", "name": "ReviewAnalyzer", "type": "shopmaibeli.reviewAnalyzer", "typeVersion": 1.0, "position": [440, 200], "parameters": {}},
        {"id": "5", "name": "Convert to File", "type": "n8n-nodes-base.convertToFile", "typeVersion": 1.1, "position": [660, 200], "parameters": {"sourceProperty": "products", "options": {"fileName": "out.html"}}},
    ],
    "connections": {
        "Chat Trigger": {"main": [[{"node": "ProductSearch1", "type": "main", "index": 0}, {"node": "ProductSearch2", "type": "main", "index": 0}]]},
        "ProductSearch1": {"main": [[{"node": "ReviewAnalyzer", "type": "main", "index": 0}]]},
        "ProductSearch2": {"main": [[{"node": "ReviewAnalyzer", "type": "main", "index": 0}]]},
        "ReviewAnalyzer": {"main": [[{"node": "Convert to File", "type": "main", "index": 0}]]},
    }
}


def test_workflow_execution_order():
    """Workflow should produce a valid topological order."""
    wf = Workflow(SIMPLE_WORKFLOW)
    order = wf.get_execution_order()
    assert order.index("Chat Trigger") < order.index("ProductSearch")
    assert order.index("ProductSearch") < order.index("Convert to File")


def test_workflow_get_children():
    """get_children should return correct downstream nodes."""
    wf = Workflow(SIMPLE_WORKFLOW)
    children = wf.get_children("Chat Trigger")
    assert "ProductSearch" in children
    assert wf.get_children("Convert to File") == []


def test_workflow_get_parents():
    """get_parent_nodes should return correct upstream nodes."""
    wf = Workflow(SIMPLE_WORKFLOW)
    parents = wf.get_parent_nodes("ProductSearch")
    assert "Chat Trigger" in parents


@pytest.mark.asyncio
async def test_simple_workflow():
    """Executor should yield start + complete notifications for each node."""
    executor = WorkflowExecutor.from_json(SIMPLE_WORKFLOW)
    notifications = []

    async for notification in executor.execute(
        session_id="test",
        chat_history=[{"role": "user", "content": "Find earbuds"}]
    ):
        notifications.append(notification)
        assert isinstance(notification, NodeNotification)

    node_names = [n.node_name for n in notifications]
    # All three nodes should appear
    assert "Chat Trigger" in node_names
    assert "ProductSearch" in node_names
    assert "Convert to File" in node_names

    # Final node (ConvertToFile) should emit a "message" notification
    final_notifications = [n for n in notifications if n.notification_type == "message"]
    assert len(final_notifications) >= 1
    assert final_notifications[0].node_name == "Convert to File"


@pytest.mark.asyncio
async def test_parallel_execution():
    """Executor should handle parallel branches (two ProductSearch nodes at same level)."""
    executor = WorkflowExecutor.from_json(PARALLEL_WORKFLOW)
    notifications = []

    with patch.dict("os.environ", {"DEEPSEEK_API_KEY": ""}):
        async for notification in executor.execute(
            session_id="test-parallel",
            chat_history=[{"role": "user", "content": "Best laptops under $1000"}]
        ):
            notifications.append(notification)

    node_names = [n.node_name for n in notifications]
    assert "Chat Trigger" in node_names
    assert "ProductSearch1" in node_names
    assert "ProductSearch2" in node_names
    assert "ReviewAnalyzer" in node_names
    assert "Convert to File" in node_names


@pytest.mark.asyncio
async def test_workflow_executor_retry_on_failure():
    """Executor should retry a failing node and eventually record an error output."""
    from workflow_engine.executor import WorkflowExecutor

    executor = WorkflowExecutor.from_json(SIMPLE_WORKFLOW)

    call_count = 0
    original_execute_node = executor._execute_node

    async def failing_node(node_name, context):
        nonlocal call_count
        if node_name == "ProductSearch":
            call_count += 1
            if call_count < 3:
                raise RuntimeError("Simulated failure")
        return await original_execute_node(node_name, context)

    executor._execute_node = failing_node

    notifications = []
    async for notification in executor.execute(
        session_id="retry-test",
        chat_history=[{"role": "user", "content": "earbuds"}]
    ):
        notifications.append(notification)

    # Should have completed despite failures (3rd attempt succeeds)
    node_names = [n.node_name for n in notifications]
    assert "ProductSearch" in node_names

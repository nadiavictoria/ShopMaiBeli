"""Tests for individual node executors."""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from workflow_engine.models import Node, NodeInput, NodeData, NodeOutput
from workflow_engine.context import ExecutionContext


def make_node(name: str, node_type: str, parameters: dict = None) -> Node:
    return Node(
        id="test-id",
        name=name,
        type=f"shopmaibeli.{node_type}",
        type_version=1.0,
        position=(0, 0),
        parameters=parameters or {}
    )


def make_context(session_id: str = "test-session", chat_history: list = None) -> ExecutionContext:
    return ExecutionContext(
        session_id=session_id,
        chat_history=chat_history or [{"role": "user", "content": "Find wireless earbuds under $80"}]
    )


def make_input(data: dict) -> NodeInput:
    return NodeInput(ports=[[NodeData(json_data=data)]])


@pytest.mark.asyncio
async def test_chat_trigger():
    """ChatTrigger should extract the last user message from chat history."""
    from nodes.chat_trigger import ChatTriggerExecutor

    node = make_node("Chat Trigger", "chatTrigger")
    context = make_context(chat_history=[
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi!"},
        {"role": "user", "content": "Find me earbuds"},
    ])
    executor = ChatTriggerExecutor(node, workflow=None)
    output = await executor.execute(NodeInput(), context)

    assert output.first_json["chatInput"] == "Find me earbuds"
    assert output.first_json["sessionId"] == "test-session"


@pytest.mark.asyncio
async def test_product_search_mock():
    """ProductSearch should fall back to mock products when API fails."""
    from nodes.product_search import ProductSearchExecutor

    node = make_node("ProductSearch", "productSearch", {"source": "mock"})
    context = make_context()
    input_data = make_input({"chatInput": "earbuds"})
    executor = ProductSearchExecutor(node, workflow=None)
    output = await executor.execute(input_data, context)

    result = output.first_json
    assert "products" in result
    assert len(result["products"]) > 0
    assert "name" in result["products"][0]
    assert "price" in result["products"][0]


@pytest.mark.asyncio
async def test_product_search_fakestoreapi_fallback():
    """ProductSearch should use mock when fakestoreapi raises an exception."""
    from nodes.product_search import ProductSearchExecutor

    node = make_node("ProductSearch", "productSearch", {"source": "fakestoreapi"})
    context = make_context()
    input_data = make_input({"chatInput": "headphones"})
    executor = ProductSearchExecutor(node, workflow=None)

    with patch("nodes.product_search.fetch_fakestoreapi", side_effect=Exception("network error")):
        output = await executor.execute(input_data, context)

    result = output.first_json
    assert "products" in result
    assert len(result["products"]) > 0


@pytest.mark.asyncio
async def test_review_analyzer():
    """ReviewAnalyzer should add review fields to each product."""
    from nodes.review_analyzer import ReviewAnalyzerExecutor

    node = make_node("ReviewAnalyzer", "reviewAnalyzer")
    context = make_context()
    products = [
        {"name": "Product A", "price": 49.99, "rating": 4.5, "description": "Great product"},
        {"name": "Product B", "price": 29.99, "rating": 2.5, "description": "Average product"},
    ]
    input_data = make_input({"products": products})
    executor = ReviewAnalyzerExecutor(node, workflow=None)

    # No API key so it uses rule-based fallback
    with patch.dict("os.environ", {"DEEPSEEK_API_KEY": ""}):
        output = await executor.execute(input_data, context)

    result = output.first_json
    assert "products" in result
    assert len(result["products"]) == 2

    for product in result["products"]:
        assert "review_summary" in product
        assert "review_sentiment" in product
        assert "review_confidence" in product

    # High rating product should be positive
    assert result["products"][0]["review_sentiment"] == "positive"
    # Low rating product should be negative
    assert result["products"][1]["review_sentiment"] == "negative"


@pytest.mark.asyncio
async def test_convert_to_file():
    """ConvertToFile should extract content from sourceProperty and wrap in output."""
    from nodes.convert_to_file import ConvertToFileExecutor

    node = make_node("Convert to File", "convertToFile", {
        "sourceProperty": "output",
        "options": {"fileName": "report.html"}
    })
    context = make_context()
    input_data = make_input({"output": "<html><body>Report</body></html>"})
    executor = ConvertToFileExecutor(node, workflow=None)
    output = await executor.execute(input_data, context)

    result = output.first_json
    assert result["html"] == "<html><body>Report</body></html>"
    assert result["filename"] == "report.html"
    assert executor.get_notification(output, context).notification_type == "message"


@pytest.mark.asyncio
async def test_memory_buffer():
    """MemoryBufferExecutor should store and retrieve messages within window size."""
    from nodes.memory_buffer import MemoryBufferExecutor

    node = make_node("Memory", "memoryBufferWindow", {"windowSize": 2})
    context = make_context()
    executor = MemoryBufferExecutor(node, workflow=None)

    executor.add_message(context, "user", "Hello")
    executor.add_message(context, "assistant", "Hi!")
    executor.add_message(context, "user", "Find earbuds")
    executor.add_message(context, "assistant", "Sure!")
    executor.add_message(context, "user", "Under $80")

    messages = executor.get_messages(context)
    # windowSize=2 means max 4 messages (2 pairs)
    assert len(messages) <= 4

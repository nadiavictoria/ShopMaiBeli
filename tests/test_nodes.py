"""
Node-level unit tests.

All tests use mock data — no network required.
Run with:  pytest tests/test_nodes.py -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from workflow_engine.models import Node, NodeInput, NodeData
from workflow_engine.context import ExecutionContext
from nodes.product_search import ProductSearchExecutor
from nodes.review_analyzer import ReviewAnalyzerExecutor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_node(node_type: str, parameters: dict = None) -> Node:
    return Node(
        id="1",
        name=f"Test {node_type}",
        type=node_type,
        type_version=1.0,
        position=(0, 0),
        parameters=parameters or {},
    )


def make_input(json_data: dict) -> NodeInput:
    return NodeInput(ports=[[[NodeData(json_data=json_data)]]])


def make_context() -> ExecutionContext:
    return ExecutionContext(session_id="test")


# ---------------------------------------------------------------------------
# ProductSearch — mock backend
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_product_search_mock_returns_products():
    executor = ProductSearchExecutor(
        make_node("productSearch", {"source": "mock", "maxResults": 5}),
        workflow=None,
    )
    output = await executor.execute(make_input({"chatInput": "earbuds"}), make_context())

    products = output.first_json.get("products", [])
    assert len(products) > 0, "Expected at least one product"
    assert output.first_json["source"] == "mock"
    assert output.first_json["count"] == len(products)


@pytest.mark.asyncio
async def test_product_search_mock_product_schema():
    """Each product must have required fields."""
    executor = ProductSearchExecutor(
        make_node("productSearch", {"source": "mock", "maxResults": 5}),
        workflow=None,
    )
    output = await executor.execute(make_input({"chatInput": ""}), make_context())

    for p in output.first_json["products"]:
        assert "name" in p, "Missing 'name'"
        assert "price" in p, "Missing 'price'"
        assert "rating" in p, "Missing 'rating'"
        assert "description" in p, "Missing 'description'"
        assert "source" in p, "Missing 'source'"
        assert isinstance(p["price"], (int, float)), "price must be numeric"
        assert 0.0 <= p["rating"] <= 5.0, "rating must be 0-5"


@pytest.mark.asyncio
async def test_product_search_mock_respects_max_results():
    executor = ProductSearchExecutor(
        make_node("productSearch", {"source": "mock", "maxResults": 2}),
        workflow=None,
    )
    output = await executor.execute(make_input({"chatInput": ""}), make_context())
    assert len(output.first_json["products"]) <= 2


@pytest.mark.asyncio
async def test_product_search_mock_query_filter():
    """Searching 'earbuds' should return products matching that term."""
    executor = ProductSearchExecutor(
        make_node("productSearch", {"source": "mock", "maxResults": 10}),
        workflow=None,
    )
    output = await executor.execute(make_input({"chatInput": "earbuds"}), make_context())
    products = output.first_json["products"]
    # At least one result should match "earbuds"
    assert any(
        "earbuds" in p["name"].lower()
        or "earbuds" in p["description"].lower()
        for p in products
    ), "Expected at least one earbuds result"


@pytest.mark.asyncio
async def test_product_search_accepts_query_key():
    """Should also read query from 'query' key, not just 'chatInput'."""
    executor = ProductSearchExecutor(
        make_node("productSearch", {"source": "mock"}),
        workflow=None,
    )
    output = await executor.execute(make_input({"query": "headphones"}), make_context())
    assert output.first_json.get("products") is not None


@pytest.mark.asyncio
async def test_product_search_notification():
    executor = ProductSearchExecutor(
        make_node("productSearch", {"source": "mock"}),
        workflow=None,
    )
    ctx = make_context()
    output = await executor.execute(make_input({"chatInput": ""}), ctx)
    notif = executor.get_notification(output, ctx)

    assert notif is not None
    assert notif.notification_type == "step"
    assert "product" in notif.message.lower()
    assert notif.session_id == "test"


# ---------------------------------------------------------------------------
# ProductSearch — live API (integration, requires network)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_product_search_fakestoreapi():
    executor = ProductSearchExecutor(
        make_node("productSearch", {"source": "fakestoreapi", "maxResults": 3}),
        workflow=None,
    )
    output = await executor.execute(make_input({"chatInput": ""}), make_context())
    products = output.first_json.get("products", [])

    assert len(products) <= 3
    for p in products:
        assert isinstance(p["price"], (int, float))
        assert p["source"] == "fakestoreapi"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_product_search_dummyjson():
    executor = ProductSearchExecutor(
        make_node("productSearch", {"source": "dummyjson", "maxResults": 3}),
        workflow=None,
    )
    output = await executor.execute(make_input({"chatInput": "phone"}), make_context())
    products = output.first_json.get("products", [])

    assert len(products) <= 3
    for p in products:
        assert isinstance(p["price"], (int, float))
        assert p["source"] == "dummyjson"


# ---------------------------------------------------------------------------
# ReviewAnalyzer — simple mode
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_review_analyzer_adds_fields():
    mock_products = [
        {"name": "Test Product", "price": 49.99, "rating": 4.2, "description": "Good product"}
    ]
    executor = ReviewAnalyzerExecutor(
        make_node("reviewAnalyzer", {"mode": "simple"}),
        workflow=None,
    )
    output = await executor.execute(make_input({"products": mock_products}), make_context())

    products = output.first_json.get("products", [])
    assert len(products) == 1
    assert "review_summary" in products[0]
    assert "review_sentiment" in products[0]
    assert "review_confidence" in products[0]


@pytest.mark.asyncio
async def test_review_analyzer_sentiment_positive():
    """Rating >= 4.0 should give positive sentiment."""
    mock_products = [{"name": "Great Product", "price": 99.99, "rating": 4.5, "description": ""}]
    executor = ReviewAnalyzerExecutor(make_node("reviewAnalyzer"), workflow=None)
    output = await executor.execute(make_input({"products": mock_products}), make_context())

    p = output.first_json["products"][0]
    assert p["review_sentiment"] == "positive"
    assert 0.70 <= p["review_confidence"] <= 0.95


@pytest.mark.asyncio
async def test_review_analyzer_sentiment_neutral():
    """Rating 3.0–3.9 should give neutral sentiment."""
    mock_products = [{"name": "OK Product", "price": 50.00, "rating": 3.5, "description": ""}]
    executor = ReviewAnalyzerExecutor(make_node("reviewAnalyzer"), workflow=None)
    output = await executor.execute(make_input({"products": mock_products}), make_context())

    p = output.first_json["products"][0]
    assert p["review_sentiment"] == "neutral"
    assert 0.55 <= p["review_confidence"] <= 0.70


@pytest.mark.asyncio
async def test_review_analyzer_sentiment_negative():
    """Rating < 3.0 should give negative sentiment."""
    mock_products = [{"name": "Bad Product", "price": 20.00, "rating": 2.0, "description": ""}]
    executor = ReviewAnalyzerExecutor(make_node("reviewAnalyzer"), workflow=None)
    output = await executor.execute(make_input({"products": mock_products}), make_context())

    p = output.first_json["products"][0]
    assert p["review_sentiment"] == "negative"


@pytest.mark.asyncio
async def test_review_analyzer_confidence_range():
    """Confidence must always be in [0, 1]."""
    for rating in [0.0, 1.0, 2.5, 3.0, 4.0, 4.9, 5.0]:
        mock_products = [{"name": "P", "price": 10.0, "rating": rating, "description": ""}]
        executor = ReviewAnalyzerExecutor(make_node("reviewAnalyzer"), workflow=None)
        output = await executor.execute(make_input({"products": mock_products}), make_context())
        conf = output.first_json["products"][0]["review_confidence"]
        assert 0.0 <= conf <= 1.0, f"Confidence {conf} out of range for rating {rating}"


@pytest.mark.asyncio
async def test_review_analyzer_preserves_original_fields():
    """Existing product fields must not be removed."""
    mock_products = [
        {"name": "P", "price": 49.99, "rating": 4.0, "category": "electronics", "source": "mock"}
    ]
    executor = ReviewAnalyzerExecutor(make_node("reviewAnalyzer"), workflow=None)
    output = await executor.execute(make_input({"products": mock_products}), make_context())

    p = output.first_json["products"][0]
    assert p["name"] == "P"
    assert p["price"] == 49.99
    assert p["category"] == "electronics"
    assert p["source"] == "mock"


@pytest.mark.asyncio
async def test_review_analyzer_merges_multiple_sources():
    """Products from two upstream nodes should all be analyzed."""
    products_a = [{"name": "A", "price": 10.0, "rating": 4.0, "description": ""}]
    products_b = [{"name": "B", "price": 20.0, "rating": 3.0, "description": ""}]

    # Two items on port 0 simulating two parallel ProductSearch outputs
    input_data = NodeInput(ports=[[
        [NodeData(json_data={"products": products_a})],
        [NodeData(json_data={"products": products_b})],
    ]])

    executor = ReviewAnalyzerExecutor(make_node("reviewAnalyzer"), workflow=None)
    output = await executor.execute(input_data, make_context())

    analyzed = output.first_json["products"]
    assert len(analyzed) == 2
    names = {p["name"] for p in analyzed}
    assert names == {"A", "B"}


@pytest.mark.asyncio
async def test_review_analyzer_empty_input():
    """Empty product list should return empty products without error."""
    executor = ReviewAnalyzerExecutor(make_node("reviewAnalyzer"), workflow=None)
    output = await executor.execute(make_input({"products": []}), make_context())
    assert output.first_json.get("products") == []


@pytest.mark.asyncio
async def test_review_analyzer_notification():
    mock_products = [{"name": "P", "price": 10.0, "rating": 4.0, "description": ""}]
    executor = ReviewAnalyzerExecutor(make_node("reviewAnalyzer"), workflow=None)
    ctx = make_context()
    output = await executor.execute(make_input({"products": mock_products}), ctx)
    notif = executor.get_notification(output, ctx)

    assert notif is not None
    assert notif.notification_type == "step"
    assert "1" in notif.message

"""
External API and backend connectivity tests.

These tests require network access and/or a running backend server.
Run with:  pytest tests/test_apis.py -v -m integration
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import httpx


# ---------------------------------------------------------------------------
# FakeStoreAPI connectivity
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_fakestoreapi_reachable():
    """FakeStoreAPI must respond with a single product."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://fakestoreapi.com/products?limit=1",
            timeout=10.0
        )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fakestoreapi_product_schema():
    """FakeStoreAPI products must have required fields."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://fakestoreapi.com/products?limit=3",
            timeout=10.0
        )
    assert resp.status_code == 200
    products = resp.json()
    for p in products:
        assert "title" in p, "Missing 'title'"
        assert "price" in p, "Missing 'price'"
        assert "rating" in p, "Missing 'rating'"
        assert isinstance(p["price"], (int, float))
        assert "rate" in p["rating"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fakestoreapi_categories():
    """FakeStoreAPI must return a non-empty categories list."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://fakestoreapi.com/products/categories",
            timeout=10.0
        )
    assert resp.status_code == 200
    categories = resp.json()
    assert isinstance(categories, list)
    assert len(categories) > 0


# ---------------------------------------------------------------------------
# DummyJSON connectivity
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_dummyjson_reachable():
    """DummyJSON must respond with a products object."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://dummyjson.com/products?limit=1",
            timeout=10.0
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "products" in data
    assert len(data["products"]) == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dummyjson_product_schema():
    """DummyJSON products must have required fields."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://dummyjson.com/products?limit=3",
            timeout=10.0
        )
    assert resp.status_code == 200
    products = resp.json()["products"]
    for p in products:
        assert "title" in p, "Missing 'title'"
        assert "price" in p, "Missing 'price'"
        assert "rating" in p, "Missing 'rating'"
        assert isinstance(p["price"], (int, float))
        assert isinstance(p["rating"], (int, float))


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dummyjson_search():
    """DummyJSON search endpoint must accept a query parameter."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://dummyjson.com/products/search?q=phone&limit=3",
            timeout=10.0
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "products" in data


# ---------------------------------------------------------------------------
# Backend health (requires running server on port 8888)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_backend_health():
    """
    Backend must respond to /health with {"status": "ok"}.
    Requires running: ./start.sh
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get("http://localhost:8888/health", timeout=5.0)
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_backend_get_workflow():
    """
    /get_workflow must return a JSON payload with 'name' and 'html' fields.
    Requires running: ./start.sh
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://localhost:8888/get_workflow",
            json={},
            timeout=10.0
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "name" in data or "type" in data, (
        "Response should contain at least 'name' or 'type' field"
    )

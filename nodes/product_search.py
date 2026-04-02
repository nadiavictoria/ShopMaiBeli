"""
ProductSearchExecutor - fetches product data from external APIs.

Supports three backends:
  fakestoreapi  https://fakestoreapi.com
  dummyjson     https://dummyjson.com
  mock          hardcoded test data (no network required)
"""

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import httpx

from workflow_engine.models import NodeInput, NodeNotification, NodeOutput
from .base import BaseNodeExecutor

if TYPE_CHECKING:
    from workflow_engine.context import ExecutionContext

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 15  # seconds


class ProductSearchExecutor(BaseNodeExecutor):
    """
    Fetches products from a configurable data source.

    Workflow JSON parameters
    -----------------------
    source      str   "fakestoreapi" | "dummyjson" | "mock"   default: "fakestoreapi"
    category    str   Optional category filter                 default: None
    maxResults  int   Max products to return                   default: 10

    Input (from parent node, e.g. QueryAnalyzer or ChatTrigger)
    -----------------------------------------------------------
    first_json may contain:
      chatInput  str   raw user query
      query      str   extracted query (alternative key)
      category   str   extracted category (overrides parameter)
    """

    node_type = "productSearch"

    async def execute(
        self,
        input_data: NodeInput,
        context: "ExecutionContext",
    ) -> NodeOutput:
        # --- Read parameters from workflow JSON ---
        source = self.get_parameter("source", "fakestoreapi")
        category = self.get_parameter("category", None)
        max_results = int(self.get_parameter("maxResults", 10))

        # --- Get search query and optional category override from input ---
        input_json = input_data.first_json
        query = input_json.get("chatInput", "") or input_json.get("query", "")
        # If upstream node extracted a category, prefer it
        category = input_json.get("category", category)

        logger.info(
            f"[{self.node.name}] source={source!r}, query={query!r}, "
            f"category={category!r}, maxResults={max_results}"
        )

        try:
            if source == "fakestoreapi":
                products = await self._fetch_fakestoreapi(category, max_results)
            elif source == "dummyjson":
                products = await self._fetch_dummyjson(query, category, max_results)
            else:
                products = self._get_mock_products(query, max_results)

            logger.info(f"[{self.node.name}] found {len(products)} products from {source!r}")

        except Exception as exc:
            logger.warning(f"[{self.node.name}] {source!r} failed ({exc}), falling back to dummyjson")
            try:
                products = await self._fetch_dummyjson(query, category, max_results)
                source = "dummyjson (fallback)"
                logger.info(f"[{self.node.name}] fallback found {len(products)} products")
            except Exception as exc2:
                logger.warning(f"[{self.node.name}] dummyjson also failed ({exc2}), using mock data")
                products = self._get_mock_products(query, max_results)
                source = "mock (fallback)"

        return self.create_output({
            "products": products,
            "source": source,
            "count": len(products),
        })

    # ------------------------------------------------------------------
    # Backend implementations
    # ------------------------------------------------------------------

    async def _fetch_fakestoreapi(
        self,
        category: Optional[str],
        max_results: int,
    ) -> List[Dict[str, Any]]:
        """GET https://fakestoreapi.com/products[/category/<cat>]"""
        url = "https://fakestoreapi.com/products"
        if category:
            url += f"/category/{category}"

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            raw = resp.json()

        return [
            {
                "name": p["title"],
                "price": p["price"],
                "rating": p.get("rating", {}).get("rate", 0),
                "description": p["description"],
                "category": p.get("category", ""),
                "source": "fakestoreapi",
            }
            for p in raw[:max_results]
        ]

    async def _fetch_dummyjson(
        self,
        query: str,
        category: Optional[str],
        max_results: int,
    ) -> List[Dict[str, Any]]:
        """
        GET https://dummyjson.com/products/search?q=<query>  (if query given)
        GET https://dummyjson.com/products/category/<cat>    (if category given)
        GET https://dummyjson.com/products                   (fallback)
        """
        if query:
            url = f"https://dummyjson.com/products/search?q={query}&limit={max_results}"
        elif category:
            url = f"https://dummyjson.com/products/category/{category}?limit={max_results}"
        else:
            url = f"https://dummyjson.com/products?limit={max_results}"

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        return [
            {
                "name": p["title"],
                "price": p["price"],
                "rating": p.get("rating", 0),
                "description": p.get("description", ""),
                "category": p.get("category", ""),
                "source": "dummyjson",
            }
            for p in data.get("products", [])
        ]

    def _get_mock_products(
        self,
        query: str,
        max_results: int,
    ) -> List[Dict[str, Any]]:
        """Return hardcoded test data — no network required."""
        all_products = [
            {
                "name": "Test Earbuds Pro",
                "price": 49.99,
                "rating": 4.2,
                "description": "Great noise cancellation, 24 h battery",
                "category": "electronics",
                "source": "mock",
            },
            {
                "name": "Budget Earbuds",
                "price": 29.99,
                "rating": 3.8,
                "description": "Good value option, IPX4 water-resistant",
                "category": "electronics",
                "source": "mock",
            },
            {
                "name": "Premium Wireless Headphones",
                "price": 89.99,
                "rating": 4.6,
                "description": "Studio-quality sound, 30 h battery, ANC",
                "category": "electronics",
                "source": "mock",
            },
            {
                "name": "Smart Watch Fitness",
                "price": 129.99,
                "rating": 4.4,
                "description": "Heart rate, GPS, sleep tracking",
                "category": "wearables",
                "source": "mock",
            },
            {
                "name": "Portable Charger 20000mAh",
                "price": 39.99,
                "rating": 4.5,
                "description": "Fast charge, USB-C PD, dual output",
                "category": "accessories",
                "source": "mock",
            },
        ]

        if query:
            q = query.lower()
            filtered = [
                p for p in all_products
                if q in p["name"].lower()
                or q in p["description"].lower()
                or q in p["category"].lower()
            ]
            return filtered[:max_results] if filtered else all_products[:max_results]

        return all_products[:max_results]

    # ------------------------------------------------------------------
    # Notification
    # ------------------------------------------------------------------

    def get_notification(
        self,
        output: NodeOutput,
        context: "ExecutionContext",
    ) -> Optional[NodeNotification]:
        count = output.first_json.get("count", 0)
        source = output.first_json.get("source", "unknown")
        return NodeNotification(
            node_name=self.node.name,
            session_id=context.session_id,
            message=f"Found {count} product(s) from {source}.",
            notification_type="step",
        )

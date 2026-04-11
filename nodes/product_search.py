"""
ProductSearchExecutor - fetches product data from external APIs.

Supports three backends:
  fakestoreapi  https://fakestoreapi.com
  dummyjson     https://dummyjson.com
  mock          hardcoded test data (no network required)
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from urllib.parse import quote

import httpx

from workflow_engine.models import NodeInput, NodeNotification, NodeOutput
from .base import BaseNodeExecutor

if TYPE_CHECKING:
    from workflow_engine.context import ExecutionContext

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 15  # seconds

# Map common product category terms → DummyJSON category slugs
_DUMMYJSON_CATEGORY_MAP = {
    "bag": "womens-bags",
    "bags": "womens-bags",
    "handbag": "womens-bags",
    "handbags": "womens-bags",
    "purse": "womens-bags",
    "tote": "womens-bags",
    "backpack": "womens-bags",
    "laptop": "laptops",
    "phone": "smartphones",
    "smartphone": "smartphones",
    "mobile": "smartphones",
    "watch": "mens-watches",
    "smartwatch": "mens-watches",
    "shirt": "mens-shirts",
    "dress": "womens-dresses",
    "shoes": "womens-shoes",
    "sneakers": "mens-shoes",
    "furniture": "furniture",
    "sofa": "furniture",
    "beauty": "beauty",
    "makeup": "beauty",
    "skincare": "skin-care",
    "fragrance": "fragrances",
    "perfume": "fragrances",
    "grocery": "groceries",
    "food": "groceries",
    "vehicle": "vehicle",
    "motorcycle": "motorcycle",
    "sunglasses": "sunglasses",
    "jewelry": "womens-jewellery",
    "jewellery": "womens-jewellery",
    "electronics": "laptops",
    "headphones": "mobile-accessories",
    "earbuds": "mobile-accessories",
}


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

    @staticmethod
    def _extract_structured_output(output_raw: str) -> Optional[Dict[str, Any]]:
        """
        Extract a JSON object from agent output.

        Agents may return plain JSON or a fenced code block like:
        ```json
        {...}
        ```
        """
        if not output_raw or not isinstance(output_raw, str):
            return None

        text = re.sub(r"```(?:json)?\s*", "", output_raw)
        text = re.sub(r"```\s*", "", text).strip()

        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, TypeError):
            pass

        start = text.find("{")
        if start == -1:
            return None

        depth = 0
        for index, char in enumerate(text[start:], start):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start:index + 1])
                        return parsed if isinstance(parsed, dict) else None
                    except (json.JSONDecodeError, TypeError):
                        return None

        return None

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
        category = input_json.get("category", category)

        # QueryAnalyzer outputs {"output": "{...json...}"} — parse it to extract
        # product_category and use it as the search query when nothing else is set
        output_raw = input_json.get("output", "")
        if output_raw and isinstance(output_raw, str):
            parsed = self._extract_structured_output(output_raw)
            if parsed:
                query = query or parsed.get("product_category", "") or ""
                category = category or parsed.get("product_category", None)
            elif not query:
                # output is already plain text (e.g. Markdown) — use as query
                query = output_raw[:100]

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
        Prefer category search (more relevant) over keyword search.
        Maps common product terms to DummyJSON category slugs.
        Falls back to keyword search, then general listing.
        """
        # Try to resolve a DummyJSON category slug from query or category
        slug = None
        for term in [category, query]:
            if term:
                slug = _DUMMYJSON_CATEGORY_MAP.get(term.lower().strip())
                if slug:
                    break

        if slug:
            url = f"https://dummyjson.com/products/category/{slug}?limit={max_results}"
        elif query:
            url = f"https://dummyjson.com/products/search?q={quote(query)}&limit={max_results}"
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

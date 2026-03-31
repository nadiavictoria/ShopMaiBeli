import httpx
from workflow_engine.models import NodeInput, NodeOutput
from .base import BaseNodeExecutor


def get_mock_products() -> list[dict]:
    return [
        {"name": "Test Earbuds Pro", "price": 49.99, "rating": 4.2,
         "description": "Great noise cancellation, 24h battery life", "source": "mock"},
        {"name": "Budget Earbuds", "price": 29.99, "rating": 3.8,
         "description": "Good value option, decent sound quality", "source": "mock"},
        {"name": "Premium Wireless Earbuds", "price": 79.99, "rating": 4.6,
         "description": "Premium ANC, Hi-Res audio, 30h total battery", "source": "mock"},
    ]


async def fetch_fakestoreapi(category: str = None, max_results: int = 10) -> list[dict]:
    url = "https://fakestoreapi.com/products"
    if category:
        url += f"/category/{category}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        products = resp.json()[:max_results]
    return [
        {
            "name": p["title"],
            "price": p["price"],
            "rating": p.get("rating", {}).get("rate", 0),
            "description": p["description"],
            "source": "fakestoreapi",
            "url": f"https://fakestoreapi.com/products/{p['id']}"
        }
        for p in products
    ]


async def fetch_dummyjson(query: str = "", category: str = None, max_results: int = 10) -> list[dict]:
    if query:
        url = f"https://dummyjson.com/products/search?q={query}&limit={max_results}"
    elif category:
        url = f"https://dummyjson.com/products/category/{category}?limit={max_results}"
    else:
        url = f"https://dummyjson.com/products?limit={max_results}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    return [
        {
            "name": p["title"],
            "price": p["price"],
            "rating": p.get("rating", 0),
            "description": p["description"],
            "source": "dummyjson",
            "url": p.get("thumbnail", "")
        }
        for p in data.get("products", [])
    ]


class ProductSearchExecutor(BaseNodeExecutor):
    node_type = "productSearch"

    async def execute(self, input_data: NodeInput, context) -> NodeOutput:
        source = self.get_parameter("source", "fakestoreapi")
        category = self.get_parameter("category", None)
        max_results = self.get_parameter("maxResults", 10)

        input_json = input_data.first_json
        query = input_json.get("chatInput", "") or input_json.get("query", "")

        try:
            if source == "fakestoreapi":
                products = await fetch_fakestoreapi(category, max_results)
            elif source == "dummyjson":
                products = await fetch_dummyjson(query, category, max_results)
            else:
                products = get_mock_products()
        except Exception:
            products = get_mock_products()

        return self.create_output({
            "products": products,
            "source": source,
            "count": len(products),
            "query": query
        })

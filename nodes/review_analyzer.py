import os
import json
import httpx
from workflow_engine.models import NodeInput, NodeOutput
from .base import BaseNodeExecutor


class ReviewAnalyzerExecutor(BaseNodeExecutor):
    node_type = "reviewAnalyzer"

    async def execute(self, input_data: NodeInput, context) -> NodeOutput:
        input_json = input_data.first_json
        products = input_json.get("products", [])

        # Merge products from multiple parallel sources if needed
        all_items = input_data.get_items(port=0)
        if len(all_items) > 1:
            products = []
            for item in all_items:
                if hasattr(item, 'json_data'):
                    products.extend(item.json_data.get("products", []))

        analyzed = []
        for product in products:
            summary = await self._analyze_product(product)
            analyzed.append({**product, **summary})

        return self.create_output({"products": analyzed})

    async def _analyze_product(self, product: dict) -> dict:
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if api_key:
            try:
                return await self._llm_analyze(product, api_key)
            except Exception:
                pass

        # Rule-based fallback
        rating = product.get("rating", 0)
        sentiment = "positive" if rating >= 4 else ("mixed" if rating >= 3 else "negative")
        summary = (
            f"Rated {rating}/5 stars. "
            + ("Highly recommended." if rating >= 4 else "Mixed reviews." if rating >= 3 else "Some concerns noted.")
        )
        return {
            "review_summary": summary,
            "review_sentiment": sentiment,
            "review_confidence": min(float(rating) / 5.0, 1.0)
        }

    async def _llm_analyze(self, product: dict, api_key: str) -> dict:
        prompt = (
            f"Product: {product.get('name', 'Unknown')}\n"
            f"Price: ${product.get('price', 'N/A')}\n"
            f"Rating: {product.get('rating', 'N/A')}/5\n"
            f"Description: {product.get('description', 'N/A')}\n\n"
            "Write a 1-2 sentence review summary and assess sentiment. "
            'Respond as JSON: {"review_summary": "...", "review_sentiment": "positive|mixed|negative", "review_confidence": 0.0}'
        )
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 256
                }
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]

        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        return {"review_summary": text, "review_sentiment": "mixed", "review_confidence": 0.5}

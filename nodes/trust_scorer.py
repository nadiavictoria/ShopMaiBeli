"""
TrustScorerExecutor - ranks products using a composite trust score.

The score blends:
  - product rating
  - review sentiment
  - review confidence
  - price-to-value bias
  - optional source reliability bonus
"""

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from workflow_engine.models import NodeData, NodeInput, NodeNotification, NodeOutput
from .base import BaseNodeExecutor

if TYPE_CHECKING:
    from workflow_engine.context import ExecutionContext

logger = logging.getLogger(__name__)


class TrustScorerExecutor(BaseNodeExecutor):
    """
    Compute a composite trust score for each product and rank the results.

    Workflow JSON parameters
    -----------------------
    topK               int    Max ranked products to return      default: 10
    ratingWeight       float  Weight for numeric rating          default: 0.45
    sentimentWeight    float  Weight for sentiment/confidence    default: 0.25
    priceWeight        float  Weight for price-to-value bias     default: 0.20
    sourceWeight       float  Weight for source reliability      default: 0.10

    Input
    -----
    Expects upstream items carrying {"products": [...]}.

    Output
    ------
    {
      "products": [
        {
          ...original_fields,
          "trust_score": float,          # 0-100
          "trust_rank": int,             # 1-based rank
          "trust_justification": str
        },
        ...
      ]
    }
    """

    node_type = "trustScorer"

    _SOURCE_RELIABILITY = {
        "dummyjson": 0.60,
        "dummyjson (fallback)": 0.55,
        "fakestoreapi": 0.55,
        "mock": 0.35,
        "mock (fallback)": 0.30,
    }

    _SENTIMENT_SCORES = {
        "positive": 1.0,
        "neutral": 0.6,
        "negative": 0.2,
    }

    async def execute(
        self,
        input_data: NodeInput,
        context: "ExecutionContext",
    ) -> NodeOutput:
        top_k = int(self.get_parameter("topK", 10))
        rating_weight = float(self.get_parameter("ratingWeight", 0.45))
        sentiment_weight = float(self.get_parameter("sentimentWeight", 0.25))
        price_weight = float(self.get_parameter("priceWeight", 0.20))
        source_weight = float(self.get_parameter("sourceWeight", 0.10))

        all_items: List[NodeData] = input_data.get_items(port=0)
        products: List[Dict[str, Any]] = []
        for item in all_items:
            products.extend(item.json_data.get("products", []))

        logger.info(f"[{self.node.name}] scoring {len(products)} product(s)")

        if not products:
            return self.create_output({"products": []})

        prices = [float(p.get("price", 0) or 0) for p in products if isinstance(p.get("price"), (int, float))]
        min_price = min(prices) if prices else 0.0
        max_price = max(prices) if prices else 0.0

        scored = []
        for product in products:
            trust_score = self._score_product(
                product,
                min_price=min_price,
                max_price=max_price,
                rating_weight=rating_weight,
                sentiment_weight=sentiment_weight,
                price_weight=price_weight,
                source_weight=source_weight,
            )
            justification = self._build_justification(product, trust_score)
            scored.append({
                **product,
                "trust_score": round(trust_score, 2),
                "trust_justification": justification,
            })

        scored.sort(
            key=lambda p: (
                p.get("trust_score", 0),
                p.get("rating", 0),
                -float(p.get("price", 0) or 0),
            ),
            reverse=True,
        )

        for index, product in enumerate(scored, start=1):
            product["trust_rank"] = index

        return self.create_output({"products": scored[:top_k]})

    def _score_product(
        self,
        product: Dict[str, Any],
        *,
        min_price: float,
        max_price: float,
        rating_weight: float,
        sentiment_weight: float,
        price_weight: float,
        source_weight: float,
    ) -> float:
        rating = float(product.get("rating", 0) or 0)
        rating_norm = max(0.0, min(5.0, rating)) / 5.0

        sentiment = str(product.get("review_sentiment", "")).lower()
        sentiment_base = self._SENTIMENT_SCORES.get(sentiment, 0.5)
        confidence = float(product.get("review_confidence", 0.5) or 0.5)
        confidence = max(0.0, min(1.0, confidence))
        sentiment_norm = max(0.0, min(1.0, sentiment_base * (0.7 + 0.3 * confidence)))

        price = float(product.get("price", 0) or 0)
        if max_price > min_price:
            price_norm = 1.0 - ((price - min_price) / (max_price - min_price))
        else:
            price_norm = 1.0
        price_norm = max(0.0, min(1.0, price_norm))

        source = str(product.get("source", "")).lower()
        source_norm = self._SOURCE_RELIABILITY.get(source, 0.5)

        weighted = (
            rating_weight * rating_norm +
            sentiment_weight * sentiment_norm +
            price_weight * price_norm +
            source_weight * source_norm
        )
        return max(0.0, min(100.0, weighted * 100))

    def _build_justification(self, product: Dict[str, Any], trust_score: float) -> str:
        rating = product.get("rating", "N/A")
        sentiment = product.get("review_sentiment", "unknown")
        price = product.get("price", "N/A")
        return (
            f"Trust score {trust_score:.1f}/100 based on rating {rating}, "
            f"{sentiment} review signal, and price ${price}."
        )

    def get_notification(
        self,
        output: NodeOutput,
        context: "ExecutionContext",
    ) -> Optional[NodeNotification]:
        count = len(output.first_json.get("products", []))
        return NodeNotification(
            node_name=self.node.name,
            session_id=context.session_id,
            message=f"Ranked {count} product(s) with trust scores.",
            notification_type="step",
        )

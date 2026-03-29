"""
ReviewAnalyzerExecutor - analyzes product reviews and ratings.

Two modes
---------
simple  (default) Derives review_summary, review_sentiment, and
                  review_confidence from each product's numeric rating.
                  No external calls required.

rag     (future)  Queries a FAISS vector index built over real review
                  data in data/reviews/. Placeholder only for now —
                  falls back to simple mode.
"""

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from workflow_engine.models import NodeData, NodeInput, NodeNotification, NodeOutput
from .base import BaseNodeExecutor

if TYPE_CHECKING:
    from workflow_engine.context import ExecutionContext

logger = logging.getLogger(__name__)


class ReviewAnalyzerExecutor(BaseNodeExecutor):
    """
    Enriches product data with review analysis.

    Workflow JSON parameters
    -----------------------
    mode    str   "simple" | "rag"   default: "simple"

    Input (from ProductSearch or multiple ProductSearch nodes)
    ----------------------------------------------------------
    Expects items on port 0 each carrying {"products": [...], ...}.
    Products from multiple sources are merged before analysis.

    Output
    ------
    {"products": [...]}  — same products with three fields added per item:
      review_summary    str    Human-readable summary sentence.
      review_sentiment  str    "positive" | "neutral" | "negative"
      review_confidence float  0-1 confidence score derived from rating.
    """

    node_type = "reviewAnalyzer"

    async def execute(
        self,
        input_data: NodeInput,
        context: "ExecutionContext",
    ) -> NodeOutput:
        mode = self.get_parameter("mode", "simple")

        # Collect all products from every upstream item (may come from
        # multiple parallel ProductSearch nodes).
        all_items: List[NodeData] = input_data.get_items(port=0)
        products: List[Dict[str, Any]] = []
        for item in all_items:
            products.extend(item.json_data.get("products", []))

        logger.info(
            f"[{self.node.name}] analyzing {len(products)} product(s) "
            f"(mode={mode!r})"
        )

        if mode == "rag":
            analyzed = await self._analyze_rag(products)
        else:
            analyzed = self._analyze_simple(products)

        return self.create_output({"products": analyzed})

    # ------------------------------------------------------------------
    # Simple mode
    # ------------------------------------------------------------------

    def _analyze_simple(
        self,
        products: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Derive review fields from the numeric rating.

        Rating bands
        ~~~~~~~~~~~~
        [4.0, 5.0]  positive  confidence 0.70 – 0.95
        [3.0, 4.0)  neutral   confidence 0.55 – 0.70
        [0.0, 3.0)  negative  confidence 0.30 – 0.55
        """
        analyzed = []
        for product in products:
            rating = float(product.get("rating", 3.0))
            rating = max(0.0, min(5.0, rating))  # clamp to [0, 5]

            if rating >= 4.0:
                sentiment = "positive"
                # Linear scale: 4.0 → 0.70, 5.0 → 0.95
                confidence = round(0.70 + (rating - 4.0) * 0.25, 2)
                summary = (
                    f"Highly rated at {rating}/5 — customers report strong satisfaction "
                    f"with quality and value."
                )
            elif rating >= 3.0:
                sentiment = "neutral"
                # Linear scale: 3.0 → 0.55, 4.0 → 0.70
                confidence = round(0.55 + (rating - 3.0) * 0.15, 2)
                summary = (
                    f"Moderately rated at {rating}/5 — mixed feedback; "
                    f"adequate for most use cases."
                )
            else:
                sentiment = "negative"
                # Linear scale: 0.0 → 0.30, 3.0 → 0.55
                confidence = round(0.30 + (rating / 3.0) * 0.25, 2)
                summary = (
                    f"Low rating of {rating}/5 — notable complaints; "
                    f"consider alternatives."
                )

            analyzed.append({
                **product,
                "review_summary": summary,
                "review_sentiment": sentiment,
                "review_confidence": confidence,
            })

        return analyzed

    # ------------------------------------------------------------------
    # RAG mode (placeholder)
    # ------------------------------------------------------------------

    async def _analyze_rag(
        self,
        products: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Future: query FAISS index for real review text, then summarize.

        Would use:
          sentence-transformers  all-MiniLM-L6-v2 for embeddings
          faiss-cpu              IndexFlatIP for similarity search
          data/reviews/*.json    review corpus

        For now, falls back to simple mode.
        """
        logger.info(
            f"[{self.node.name}] RAG mode not yet implemented — "
            "falling back to simple mode"
        )
        return self._analyze_simple(products)

    # ------------------------------------------------------------------
    # Notification
    # ------------------------------------------------------------------

    def get_notification(
        self,
        output: NodeOutput,
        context: "ExecutionContext",
    ) -> Optional[NodeNotification]:
        count = len(output.first_json.get("products", []))
        return NodeNotification(
            node_name=self.node.name,
            session_id=context.session_id,
            message=f"Analyzed reviews for {count} product(s).",
            notification_type="step",
        )

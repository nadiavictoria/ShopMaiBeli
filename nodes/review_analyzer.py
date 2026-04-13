"""
ReviewAnalyzerExecutor - analyzes product reviews and ratings.

Two modes
---------
simple  (default) Derives review_summary, review_sentiment, and
                  review_confidence from each product's numeric rating.
                  No external calls required.

rag     Uses local normalized review JSON files as a lightweight
        retrieval corpus. Falls back to simple mode when no review
        matches are found.
"""

import json
import logging
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from workflow_engine.models import NodeData, NodeInput, NodeNotification, NodeOutput
from .base import BaseNodeExecutor

if TYPE_CHECKING:
    from workflow_engine.context import ExecutionContext

logger = logging.getLogger(__name__)

_DEFAULT_REVIEW_DATASETS = (
    "output/full_amazon_fashion_review.json",
    "output/amazon_reviews_sample.json",
)


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _tokenize(value: Any) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", _normalize_text(value))
        if len(token) >= 3
    }


def _rating_to_sentiment(rating: float) -> tuple[str, float]:
    rating = max(0.0, min(5.0, float(rating)))
    if rating >= 4.0:
        return "positive", round(0.70 + (rating - 4.0) * 0.25, 2)
    if rating >= 3.0:
        return "neutral", round(0.55 + (rating - 3.0) * 0.15, 2)
    return "negative", round(0.30 + (rating / 3.0) * 0.25, 2)


@lru_cache(maxsize=8)
def _load_review_corpus(path_key: tuple[str, ...]) -> list[dict[str, Any]]:
    corpus: list[dict[str, Any]] = []

    for raw_path in path_key:
        path = Path(raw_path)
        if not path.exists():
            logger.info("[reviewAnalyzer] review dataset not found: %s", path)
            continue

        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        if not isinstance(data, list):
            logger.warning("[reviewAnalyzer] review dataset is not a JSON list: %s", path)
            continue

        for row in data:
            if not isinstance(row, dict):
                continue

            product_name = str(row.get("product_name", "")).strip()
            review_text = str(row.get("review_text", "")).strip()
            if not product_name or not review_text:
                continue

            search_text = " ".join(
                value
                for value in [
                    product_name,
                    str(row.get("brand", "")).strip(),
                    str(row.get("source", "")).strip(),
                    str(row.get("source_dataset", "")).strip(),
                ]
                if value
            )
            corpus.append({
                "product_name": product_name,
                "review_text": review_text,
                "rating": float(row.get("rating", 0) or 0),
                "brand": str(row.get("brand", "")).strip(),
                "source": str(row.get("source", "")).strip(),
                "tokens": _tokenize(search_text),
            })

    logger.info(
        "[reviewAnalyzer] loaded %s review rows from %s dataset(s)",
        len(corpus),
        len(path_key),
    )
    return corpus


class ReviewAnalyzerExecutor(BaseNodeExecutor):
    """
    Enriches product data with review analysis.

    Workflow JSON parameters
    -----------------------
    mode         str   "simple" | "rag"   default: "rag"
    datasetPath  str   Optional JSON review corpus path
    datasetPaths list  Optional list of JSON review corpus paths

    Input (from ProductSearch or multiple ProductSearch nodes)
    ----------------------------------------------------------
    Expects items on port 0 each carrying {"products": [...], ...}.
    Products from multiple sources are merged before analysis.

    Output
    ------
    {"products": [...]}  — same products with review fields added per item.
    """

    node_type = "reviewAnalyzer"

    async def execute(
        self,
        input_data: NodeInput,
        context: "ExecutionContext",
    ) -> NodeOutput:
        mode = self.get_parameter("mode", "rag")

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

    def _analyze_simple(
        self,
        products: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        analyzed = []
        for product in products:
            rating = max(0.0, min(5.0, float(product.get("rating", 3.0))))
            sentiment, confidence = _rating_to_sentiment(rating)

            if sentiment == "positive":
                summary = (
                    f"Highly rated at {rating}/5 — customers report strong satisfaction "
                    f"with quality and value."
                )
            elif sentiment == "neutral":
                summary = (
                    f"Moderately rated at {rating}/5 — mixed feedback; "
                    f"adequate for most use cases."
                )
            else:
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

    async def _analyze_rag(
        self,
        products: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        corpus = _load_review_corpus(tuple(self._resolve_dataset_paths()))
        if not corpus:
            logger.info("[%s] no review corpus available; falling back to simple mode", self.node.name)
            return self._analyze_simple(products)

        analyzed: List[Dict[str, Any]] = []
        for product in products:
            matches = self._retrieve_reviews(product, corpus)
            if not matches:
                fallback = self._analyze_simple([product])[0]
                fallback["review_source"] = "simple_fallback"
                analyzed.append(fallback)
                continue

            avg_rating = round(sum(match["rating"] for match in matches) / len(matches), 2)
            sentiment, confidence = _rating_to_sentiment(avg_rating)
            aspects = self._extract_aspects(matches)
            snippets = "; ".join(
                match["review_text"][:160].strip()
                for match in matches[:2]
            )
            summary = (
                f"Matched {len(matches)} similar review(s) averaging {avg_rating}/5. "
                f"Common themes: {aspects}. Sample feedback: {snippets}"
            )

            analyzed.append({
                **product,
                "review_summary": summary,
                "review_sentiment": sentiment,
                "review_confidence": confidence,
                "review_source": "rag",
                "review_matches": [
                    {
                        "product_name": match["product_name"],
                        "rating": match["rating"],
                        "source": match["source"],
                    }
                    for match in matches
                ],
            })

        return analyzed

    def _resolve_dataset_paths(self) -> list[str]:
        raw_paths = self.get_parameter("datasetPaths", None)
        if isinstance(raw_paths, list):
            paths = [str(path) for path in raw_paths if path]
        else:
            single_path = self.get_parameter("datasetPath", None)
            paths = [str(single_path)] if single_path else []

        if paths:
            return paths

        base_dir = Path(__file__).resolve().parents[1]
        return [str(base_dir / rel_path) for rel_path in _DEFAULT_REVIEW_DATASETS]

    def _retrieve_reviews(
        self,
        product: Dict[str, Any],
        corpus: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        query_tokens = _tokenize(
            " ".join(
                str(product.get(key, ""))
                for key in ("name", "description", "category")
            )
        )
        if not query_tokens:
            return []

        scored: list[tuple[int, dict[str, Any]]] = []
        product_name = _normalize_text(product.get("name", ""))
        for row in corpus:
            overlap = query_tokens & row["tokens"]
            if not overlap:
                continue

            score = len(overlap) * 10
            row_name = _normalize_text(row["product_name"])
            if product_name and (product_name in row_name or row_name in product_name):
                score += 25
            scored.append((score, row))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [row for score, row in scored[:3] if score >= 10]

    def _extract_aspects(self, matches: List[Dict[str, Any]]) -> str:
        stopwords = {
            "and", "with", "that", "this", "they", "them", "have", "from", "were",
            "been", "into", "very", "just", "than", "then", "when", "what",
            "your", "about", "would", "could", "should", "there", "their",
            "product", "products", "great", "good", "nice", "really", "after",
            "before", "because", "review", "reviews", "amazon", "fashion",
        }
        counter: Counter[str] = Counter()
        for match in matches:
            for token in _tokenize(match["review_text"]):
                if token not in stopwords:
                    counter[token] += 1

        top_tokens = [token for token, _count in counter.most_common(4)]
        return ", ".join(top_tokens) if top_tokens else "general product quality"

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

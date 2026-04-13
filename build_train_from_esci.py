"""
Build ShopMaiBeli training data from the Amazon ESCI shopping queries dataset.

This script:
1. Loads ESCI examples/products from parquet or CSV.
2. Maps real ESCI queries into the reduced categories:
   fashion, beauty, electronics, cellphone.
3. Scores query specificity and samples each category with a target mix.
4. Optionally rewrites queries into natural shopping-assistant prompts using
   OpenRouter (`openai/gpt-oss-120b:free`).
5. Generates validated workflow JSON objects.
6. Writes final `train.jsonl` rows with exactly:
   {"instruction": "...", "output": "{...json string...}"}

Example:
    python build_train_from_esci.py --out train_from_esci.jsonl --per-category 20
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import tempfile
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from openai import OpenAI


DEFAULT_CACHE_DIR = Path(".cache/esci")
DEFAULT_OUTPUT_PATH = Path("data/workflows/expanded_train_from_esci.jsonl")
DEFAULT_ESCI_EXAMPLES_URL = (
    "https://raw.githubusercontent.com/amazon-science/esci-data/main/"
    "shopping_queries_dataset/shopping_queries_dataset_examples.parquet"
)
DEFAULT_ESCI_PRODUCTS_URL = (
    "https://raw.githubusercontent.com/amazon-science/esci-data/main/"
    "shopping_queries_dataset/shopping_queries_dataset_products.parquet"
)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "openai/gpt-oss-120b:free"
OPENROUTER_REFERER = "https://shopmaibeli.local"
OPENROUTER_TITLE = "ShopMaiBeli ESCI Train Builder"

REDUCED_CATEGORIES = ("fashion", "beauty", "electronics", "cellphone")
TARGET_BUCKET_RATIOS = {
    "broad": 0.65,
    "medium": 0.25,
    "specific": 0.10,
}

CATEGORY_KEYWORDS = {
    "fashion": [
        "dress", "shirt", "shoes", "sneakers", "boots", "sandals",
        "bag", "bags", "handbag", "handbags", "purse", "tote",
        "wallet", "jewelry", "jewellery", "necklace", "ring",
        "bracelet", "watch", "fashion", "clothing", "jacket", "skirt",
    ],
    "beauty": [
        "makeup", "beauty", "lipstick", "foundation", "mascara",
        "skincare", "skin care", "cleanser", "moisturizer",
        "serum", "sunscreen", "perfume", "fragrance", "cologne",
        "shampoo", "conditioner", "cosmetic",
    ],
    "electronics": [
        "headset", "headphones", "earbuds", "speaker", "tv",
        "monitor", "camera", "laptop", "keyboard", "mouse",
        "tablet", "gaming", "console", "printer", "electronics",
    ],
    "cellphone": [
        "phone", "smartphone", "iphone", "android", "samsung",
        "charger", "charging cable", "usb c cable", "phone case",
        "screen protector", "power bank", "mag safe", "magsafe",
        "mobile accessories", "cell phone",
    ],
}

CELLPHONE_PRIORITY_SIGNALS = {
    "phone",
    "iphone",
    "android",
    "charger",
    "phone case",
    "screen protector",
    "power bank",
    "cell phone",
    "smartphone",
    "charging cable",
    "usb c cable",
    "magsafe",
    "mag safe",
}

REDUCED_TO_AMAZON_CATEGORIES = {
    "fashion": {"Clothing_Shoes_and_Jewelry", "Amazon_Fashion"},
    "beauty": {"All_Beauty", "Beauty_and_Personal_Care", "Health_and_Personal_Care"},
    "electronics": {"Electronics"},
    "cellphone": {"Cell_Phones_and_Accessories"},
}

GENERAL_SHOPPING_WORDS = {
    "best", "good", "cheap", "budget", "affordable", "nice", "great",
    "quality", "quality", "decent", "value", "popular", "top",
}
USE_CASE_PHRASES = {
    "for daily use", "for work", "for travel", "for office", "for home",
    "for gaming", "for school", "for running", "for gym", "for men",
    "for women", "for kids",
}
COLOR_MATERIAL_SIZE_WORDS = {
    "black", "white", "blue", "red", "pink", "green", "silver", "gold",
    "leather", "cotton", "denim", "silicone", "plastic", "metal", "wood",
    "small", "medium", "large", "xl", "xxl", "mini", "pro", "max",
}
COMMON_BRANDS = {
    "apple", "samsung", "sony", "canon", "nikon", "dell", "hp", "lenovo",
    "asus", "acer", "logitech", "anker", "belkin", "nike", "adidas",
    "puma", "reebok", "coach", "fossil", "sephora", "maybelline",
    "loreal", "olay", "cerave", "neutrogena", "cetaphil", "dove",
    "pantene", "tresemme", "becca", "fitbit", "jbl", "bose",
}

QUERY_ANALYZER_SYSTEM_MESSAGE = (
    "You are a shopping query analyzer. Extract product_category, budget, "
    "priorities, preferred_brands. Output JSON."
)
REPORT_GENERATOR_SYSTEM_MESSAGE = (
    "You are a shopping report generator for a shopping assistant. You will "
    "receive a list of real products fetched from a product API, along with "
    "their prices, ratings, and review sentiments. Using ONLY the products "
    "provided in the input data, create a clear HTML comparison report. "
    "Include: a short summary header naming the category/query, a ranked "
    "product table with columns Rank, Name, Price, Rating, Sentiment, and a "
    "brief justification for the top pick. If the exact brand requested is "
    "not in the data, note that and recommend the best available "
    "alternatives. Output ONLY valid HTML with no Markdown, no code blocks, "
    "and no explanation."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build train.jsonl from Amazon ESCI shopping queries."
    )
    parser.add_argument("--examples-path", default=DEFAULT_ESCI_EXAMPLES_URL)
    parser.add_argument("--products-path", default=DEFAULT_ESCI_PRODUCTS_URL)
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--audit-out", default="")
    parser.add_argument("--per-category", type=int, default=20)
    parser.add_argument("--locale", default="")
    parser.add_argument("--split", default="")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--allow-non-ascii", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dry-run-limit", type=int, default=12)
    parser.add_argument("--skip-rewrite", action="store_true")
    parser.add_argument("--workflow-pattern", choices=("mixed", "single", "dual"), default="mixed")
    parser.add_argument("--max-results", type=int, default=8)
    parser.add_argument("--rewrite-retries", type=int, default=3)
    parser.add_argument("--request-timeout", type=float, default=45.0)
    return parser.parse_args()


def is_url(value: str) -> bool:
    parsed = urllib.parse.urlparse(value)
    return parsed.scheme in {"http", "https"}


def is_git_lfs_pointer(path: Path) -> bool:
    if not path.exists() or path.stat().st_size > 1024:
        return False
    try:
        text = path.read_text("utf-8", errors="replace")
    except Exception:
        return False
    return text.startswith("version https://git-lfs.github.com/spec/v1")


def to_media_github_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)

    if parsed.netloc == "raw.githubusercontent.com":
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 4:
            owner, repo, branch = parts[:3]
            remainder = "/".join(parts[3:])
            return f"https://media.githubusercontent.com/media/{owner}/{repo}/{branch}/{remainder}"

    if parsed.netloc == "github.com":
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 5 and parts[2] in {"blob", "raw"}:
            owner, repo, _, branch = parts[:4]
            remainder = "/".join(parts[4:])
            return f"https://media.githubusercontent.com/media/{owner}/{repo}/{branch}/{remainder}"

    return url


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(response.read())
        temp_path = Path(tmp.name)
    temp_path.replace(destination)


def ensure_local_file(path_or_url: str, cache_dir: Path) -> Path:
    if not is_url(path_or_url):
        path = Path(path_or_url)
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")
        return path

    file_name = Path(urllib.parse.urlparse(path_or_url).path).name or "downloaded_file"
    destination = cache_dir / file_name
    if destination.exists() and not is_git_lfs_pointer(destination):
        return destination

    download_file(path_or_url, destination)
    if is_git_lfs_pointer(destination):
        media_url = to_media_github_url(path_or_url)
        if media_url != path_or_url:
            download_file(media_url, destination)
    return destination


def load_table(path: Path, columns: list[str] | None = None, label: str = "table") -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        print(f"[load] reading {label} CSV: {path}")
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if columns:
            rows = [{key: row.get(key) for key in columns} for row in rows]
        print(f"[load] loaded {len(rows)} {label} rows")
        return rows

    if suffix == ".parquet":
        try:
            import pandas as pd
        except ImportError as exc:
            raise RuntimeError(
                "Reading parquet requires pandas and a parquet engine such as pyarrow."
            ) from exc

        try:
            print(f"[load] reading {label} parquet: {path}")
            if columns:
                print(f"[load] requested columns for {label}: {', '.join(columns)}")
            df = pd.read_parquet(path, columns=columns)
        except Exception as exc:
            if is_git_lfs_pointer(path):
                raise RuntimeError(
                    "Downloaded file is a Git LFS pointer, not real parquet content."
                ) from exc
            if columns:
                try:
                    print(f"[load] requested columns not available for {label}; retrying full parquet load")
                    df = pd.read_parquet(path)
                except Exception as retry_exc:
                    raise RuntimeError(
                        f"Failed to read parquet file {path}. Make sure pandas and pyarrow are installed."
                    ) from retry_exc
            else:
                raise RuntimeError(
                    f"Failed to read parquet file {path}. Make sure pandas and pyarrow are installed."
                ) from exc
        rows = df.to_dict(orient="records")
        print(f"[load] loaded {len(rows)} {label} rows")
        return rows

    raise ValueError(f"Unsupported input format for {path}")


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def lower_text(value: Any) -> str:
    return normalize_text(value).casefold()


def slugify_text(value: str) -> str:
    text = lower_text(value)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "shopping_report"


def is_ascii_text(value: str) -> bool:
    return all(ord(ch) < 128 for ch in value)


def first_present(row: dict[str, Any], candidates: Iterable[str]) -> Any:
    for key in candidates:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def normalize_locale(value: str) -> str:
    return lower_text(value).replace("-", "_")


def normalize_split(value: str) -> str:
    return lower_text(value)


def build_product_index(products: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for row in products:
        product_id = normalize_text(first_present(row, ("product_id", "asin", "item_id")))
        locale = normalize_locale(first_present(row, ("product_locale", "locale")) or "")
        if not product_id:
            continue
        index[(product_id, locale)] = row
        if locale:
            index.setdefault((product_id, ""), row)
    return index


def collect_source_categories(product_row: dict[str, Any] | None) -> set[str]:
    if not product_row:
        return set()

    source_categories: set[str] = set()
    for key in (
        "product_category",
        "category",
        "categories",
        "browse_node",
        "product_type",
        "product_group",
        "vertical",
    ):
        value = product_row.get(key)
        if isinstance(value, list):
            for item in value:
                text = normalize_text(item)
                if text:
                    source_categories.add(text)
        else:
            text = normalize_text(value)
            if text:
                for piece in re.split(r"[|,;/]+", text):
                    piece = normalize_text(piece)
                    if piece:
                        source_categories.add(piece)
    return source_categories


def extract_examples(
    example_rows: list[dict[str, Any]],
    product_index: dict[tuple[str, str], dict[str, Any]],
    locale_filter: str,
    split_filter: str,
) -> list[dict[str, Any]]:
    locale_filter = normalize_locale(locale_filter)
    split_filter = normalize_split(split_filter)
    extracted: list[dict[str, Any]] = []

    for row in example_rows:
        query = normalize_text(first_present(row, ("query", "query_text", "search_term")))
        query_id = normalize_text(first_present(row, ("query_id", "queryId", "example_id")))
        locale = normalize_locale(first_present(row, ("query_locale", "locale", "product_locale")) or "")
        split = normalize_split(first_present(row, ("split", "dataset_split")) or "")
        product_id = normalize_text(first_present(row, ("product_id", "asin", "item_id")))
        esci_label = normalize_text(first_present(row, ("esci_label", "label", "labels")))

        if not query:
            continue
        if locale_filter and locale != locale_filter:
            continue
        if split_filter and split != split_filter:
            continue

        product_row = product_index.get((product_id, locale)) or product_index.get((product_id, ""))
        product_title = normalize_text(first_present(product_row or {}, ("product_title", "title", "product_name")))
        product_brand = normalize_text(first_present(product_row or {}, ("product_brand", "brand", "brand_name")))
        source_categories = sorted(collect_source_categories(product_row))

        extracted.append(
            {
                "query": query,
                "query_id": query_id,
                "locale": locale,
                "split": split,
                "product_id": product_id,
                "product_title": product_title,
                "product_brand": product_brand,
                "esci_label": esci_label,
                "source_categories": source_categories,
            }
        )
    return extracted


def phrase_matches(text: str, phrase: str) -> bool:
    return re.search(r"\b" + re.escape(phrase.casefold()) + r"\b", text) is not None


def score_keyword_matches(text: str, phrases: Iterable[str]) -> int:
    score = 0
    for phrase in phrases:
        if phrase_matches(text, phrase):
            score += max(1, len(phrase.split()))
    return score


def map_category(row: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    query_text = lower_text(row.get("query"))
    title_text = lower_text(row.get("product_title"))
    brand_text = lower_text(row.get("product_brand"))
    combined = " ".join(part for part in (query_text, title_text, brand_text) if part).strip()
    source_categories = set(row.get("source_categories") or [])

    detail: dict[str, Any] = {
        "source_category_hit": None,
        "keyword_scores": {},
        "reason": "",
    }

    if not combined:
        detail["reason"] = "empty_text"
        return None, detail

    category_scores = {category: 0 for category in REDUCED_CATEGORIES}
    query_scores = {
        category: score_keyword_matches(query_text, CATEGORY_KEYWORDS[category])
        for category in REDUCED_CATEGORIES
    }
    metadata_scores = {
        category: score_keyword_matches(" ".join(part for part in (title_text, brand_text) if part), CATEGORY_KEYWORDS[category])
        for category in REDUCED_CATEGORIES
    }

    detail["query_scores"] = query_scores
    detail["metadata_scores"] = metadata_scores

    for reduced_category, aligned_categories in REDUCED_TO_AMAZON_CATEGORIES.items():
        aligned_hits = source_categories.intersection(aligned_categories)
        if aligned_hits:
            category_scores[reduced_category] += 3
            detail["source_category_hit"] = sorted(aligned_hits)

    keyword_scores = {}
    detail["keyword_scores"] = keyword_scores
    for category in REDUCED_CATEGORIES:
        keyword_scores[category] = query_scores[category] + min(metadata_scores[category], 2)
        category_scores[category] += query_scores[category]
        category_scores[category] += min(metadata_scores[category], 2)

    if any(phrase_matches(combined, signal) for signal in CELLPHONE_PRIORITY_SIGNALS):
        if category_scores["cellphone"] > 0:
            category_scores["cellphone"] += 3

    if max(query_scores.values(), default=0) <= 0:
        detail["reason"] = "no_query_keyword_signal"
        return None, detail

    ordered = sorted(category_scores.items(), key=lambda item: item[1], reverse=True)
    best_category, best_score = ordered[0]
    second_score = ordered[1][1] if len(ordered) > 1 else 0

    if best_score <= 0:
        detail["reason"] = "no_signal"
        return None, detail

    if best_score == second_score and best_score < 5:
        detail["reason"] = "ambiguous_keyword_match"
        return None, detail

    if (
        best_category in {"electronics", "cellphone"}
        and category_scores["cellphone"] > 0
        and any(phrase_matches(combined, signal) for signal in CELLPHONE_PRIORITY_SIGNALS)
    ):
        best_category = "cellphone"

    detail["reason"] = "mapped"
    return best_category, detail


def title_similarity_bonus(query: str, title: str) -> int:
    query_tokens = set(re.findall(r"[a-z0-9]+", query.casefold()))
    title_tokens = set(re.findall(r"[a-z0-9]+", title.casefold()))
    if not query_tokens or not title_tokens:
        return 0
    overlap = len(query_tokens.intersection(title_tokens))
    if overlap >= min(4, len(query_tokens)):
        return 1
    return 0


def score_specificity(row: dict[str, Any]) -> tuple[int, str, dict[str, Any]]:
    query = normalize_text(row.get("query"))
    query_lower = query.casefold()
    brand = normalize_text(row.get("product_brand"))
    title = normalize_text(row.get("product_title"))

    score = 0
    detail: dict[str, Any] = {
        "matched_brand": False,
        "matched_title_like": False,
        "token_count": len(re.findall(r"[a-z0-9]+", query_lower)),
    }

    if brand and phrase_matches(query_lower, brand):
        score += 2
        detail["matched_brand"] = True

    if brand and brand.casefold() in COMMON_BRANDS:
        if phrase_matches(query_lower, brand):
            score += 1

    if re.search(r"\b[a-z]*\d+[a-z0-9-]*\b|\b\d+[a-z][a-z0-9-]*\b", query_lower):
        score += 2
        detail["has_model_token"] = True
    else:
        detail["has_model_token"] = False

    if re.search(r"\b\d+\s?(gb|tb|mb|inch|in|cm|mm|oz|ml|w|mah|pack)\b", query_lower):
        score += 2
        detail["has_size_or_storage"] = True
    else:
        detail["has_size_or_storage"] = False

    if re.search(r"\b\d+\s?(pack|pk|count|ct|pcs|piece|pieces)\b", query_lower):
        score += 1
        detail["has_pack_count"] = True
    else:
        detail["has_pack_count"] = False

    if any(phrase_matches(query_lower, word) for word in COLOR_MATERIAL_SIZE_WORDS):
        score += 1
        detail["has_color_material_size"] = True
    else:
        detail["has_color_material_size"] = False

    token_count = detail["token_count"]
    if token_count >= 6:
        score += 1
    if token_count >= 9:
        score += 1

    if any(phrase_matches(query_lower, word) for word in GENERAL_SHOPPING_WORDS):
        score -= 1
        detail["has_general_shopping_word"] = True
    else:
        detail["has_general_shopping_word"] = False

    if any(phrase in query_lower for phrase in USE_CASE_PHRASES):
        score -= 1
        detail["has_use_case_phrase"] = True
    else:
        detail["has_use_case_phrase"] = False

    if token_count <= 2:
        score -= 1

    if title and title_similarity_bonus(query, title):
        score += 1
        detail["matched_title_like"] = True

    if score <= 0:
        bucket = "broad"
    elif score <= 2:
        bucket = "medium"
    else:
        bucket = "specific"

    return score, bucket, detail


def target_bucket_counts(total: int) -> dict[str, int]:
    broad = max(1, round(total * TARGET_BUCKET_RATIOS["broad"]))
    medium = round(total * TARGET_BUCKET_RATIOS["medium"])
    specific = total - broad - medium

    if specific < 1 and total >= 3:
        specific = 1
        if broad > medium and broad > 1:
            broad -= 1
        elif medium > 0:
            medium -= 1

    counts = {"broad": broad, "medium": medium, "specific": specific}
    while sum(counts.values()) > total:
        for key in ("broad", "medium", "specific"):
            if counts[key] > 0 and sum(counts.values()) > total:
                counts[key] -= 1
    while sum(counts.values()) < total:
        counts["broad"] += 1
    return counts


def sample_queries(rows: list[dict[str, Any]], per_category: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    by_category_and_bucket: dict[str, dict[str, list[dict[str, Any]]]] = {
        category: {"broad": [], "medium": [], "specific": []}
        for category in REDUCED_CATEGORIES
    }

    for row in rows:
        by_category_and_bucket[row["reduced_category"]][row["specificity_bucket"]].append(row)

    selected: list[dict[str, Any]] = []
    for category in REDUCED_CATEGORIES:
        bucket_map = by_category_and_bucket[category]
        for bucket_rows in bucket_map.values():
            rng.shuffle(bucket_rows)

        targets = target_bucket_counts(per_category)
        category_selected: list[dict[str, Any]] = []
        leftovers: list[dict[str, Any]] = []

        for bucket in ("broad", "medium", "specific"):
            chosen = bucket_map[bucket][: targets[bucket]]
            category_selected.extend(chosen)
            leftovers.extend(bucket_map[bucket][targets[bucket]:])

        if len(category_selected) < per_category:
            rng.shuffle(leftovers)
            category_selected.extend(leftovers[: per_category - len(category_selected)])

        if len(category_selected) > per_category:
            rng.shuffle(category_selected)
            category_selected = category_selected[:per_category]

        for row in category_selected:
            row["sampling_target_mix"] = targets
        selected.extend(category_selected)

    return selected


def build_openrouter_client(api_key: str, timeout_seconds: float) -> OpenAI:
    return OpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        timeout=timeout_seconds,
    )


def rewrite_query(
    client: OpenAI,
    row: dict[str, Any],
    rewrite_retries: int,
) -> tuple[str, dict[str, Any]]:
    raw_query = normalize_text(row["query"])
    reduced_category = row["reduced_category"]
    product_brand = normalize_text(row.get("product_brand"))
    product_title = normalize_text(row.get("product_title"))
    llm_meta = {
        "provider": "openrouter",
        "base_url": OPENROUTER_BASE_URL,
        "model": OPENROUTER_MODEL,
        "attempts": 0,
    }

    system_prompt = (
        "Rewrite shopping search queries into short natural shopping-assistant "
        "requests. Preserve the original shopping intent, keep the same product "
        "category, do not invent a brand unless the original query or provided "
        "product context suggests it, and keep the request concise. Vary wording "
        "so the outputs do not all sound templated. Return only the rewritten request."
    )
    user_prompt = (
        f"Reduced category: {reduced_category}\n"
        f"Raw ESCI query: {raw_query}\n"
        f"Product brand (optional context): {product_brand or 'N/A'}\n"
        f"Product title (optional context): {product_title or 'N/A'}\n"
        "Return one short natural shopping-assistant prompt."
    )

    last_error = "rewrite_failed"
    for attempt in range(1, rewrite_retries + 1):
        llm_meta["attempts"] = attempt
        try:
            response = client.chat.completions.create(
                model=OPENROUTER_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                extra_headers={
                    "HTTP-Referer": OPENROUTER_REFERER,
                    "X-Title": OPENROUTER_TITLE,
                },
            )
            content = normalize_text(response.choices[0].message.content)
            if not content:
                raise ValueError("empty rewrite")
            content = content.strip("\"' ")
            if len(content.split()) < 2:
                raise ValueError(f"rewrite too short: {content!r}")
            return content, llm_meta
        except Exception as exc:
            last_error = str(exc)
            backoff = min(2 ** (attempt - 1), 8)
            time.sleep(backoff)

    raise RuntimeError(f"Failed to rewrite query after {rewrite_retries} attempts: {last_error}")


def choose_workflow_pattern(row: dict[str, Any], override: str) -> str:
    if override in {"single", "dual"}:
        return override
    category = row["reduced_category"]
    bucket = row["specificity_bucket"]
    if category in {"electronics", "cellphone"} or bucket == "specific":
        return "dual"
    return "single"


def product_search_category_for(reduced_category: str, source: str) -> str | None:
    if source == "dummyjson":
        mapping = {
            "fashion": "womens-bags",
            "beauty": "beauty",
            "electronics": "laptops",
            "cellphone": "smartphones",
        }
    else:
        mapping = {
            "fashion": None,
            "beauty": None,
            "electronics": "electronics",
            "cellphone": "electronics",
        }
    return mapping.get(reduced_category)


def build_workflow(row: dict[str, Any], pattern: str, max_results: int) -> dict[str, Any]:
    file_stub = slugify_text(row["instruction"])[:60]
    base_nodes = [
        {
            "id": "1",
            "name": "Chat Trigger",
            "type": "@n8n/n8n-nodes-langchain.chatTrigger",
            "typeVersion": 1.4,
            "position": [0, 200],
            "parameters": {},
        },
        {
            "id": "2",
            "name": "QueryAnalyzer",
            "type": "@n8n/n8n-nodes-langchain.agent",
            "typeVersion": 1.7,
            "position": [220, 200],
            "parameters": {
                "options": {
                    "systemMessage": QUERY_ANALYZER_SYSTEM_MESSAGE,
                }
            },
        },
        {
            "id": "3",
            "name": "DeepSeek QA",
            "type": "@n8n/n8n-nodes-langchain.lmChatDeepSeek",
            "typeVersion": 1.0,
            "position": [220, 400],
            "parameters": {},
        },
    ]

    reduced_category = row["reduced_category"]
    if pattern == "single":
        base_nodes.extend(
            [
                {
                    "id": "4",
                    "name": "ProductSearch",
                    "type": "shopmaibeli.productSearch",
                    "typeVersion": 1.0,
                    "position": [440, 200],
                    "parameters": {
                        "source": "dummyjson",
                        "maxResults": max_results,
                        "category": product_search_category_for(reduced_category, "dummyjson"),
                    },
                },
                {
                    "id": "5",
                    "name": "ReviewAnalyzer",
                    "type": "shopmaibeli.reviewAnalyzer",
                    "typeVersion": 1.0,
                    "position": [660, 200],
                    "parameters": {},
                },
                {
                    "id": "6",
                    "name": "ReportGenerator",
                    "type": "@n8n/n8n-nodes-langchain.agent",
                    "typeVersion": 1.7,
                    "position": [880, 200],
                    "parameters": {
                        "options": {"systemMessage": REPORT_GENERATOR_SYSTEM_MESSAGE},
                        "hasOutputParser": False,
                    },
                },
                {
                    "id": "7",
                    "name": "DeepSeek Report",
                    "type": "@n8n/n8n-nodes-langchain.lmChatDeepSeek",
                    "typeVersion": 1.0,
                    "position": [880, 400],
                    "parameters": {},
                },
                {
                    "id": "8",
                    "name": "Convert to File",
                    "type": "n8n-nodes-base.convertToFile",
                    "typeVersion": 1.1,
                    "position": [1100, 200],
                    "parameters": {
                        "operation": "toText",
                        "sourceProperty": "output",
                        "options": {"fileName": f"{file_stub}_report.html"},
                    },
                },
            ]
        )
        connections = {
            "Chat Trigger": {"main": [[{"node": "QueryAnalyzer", "type": "main", "index": 0}]]},
            "DeepSeek QA": {"ai_languageModel": [[{"node": "QueryAnalyzer", "type": "ai_languageModel", "index": 0}]]},
            "QueryAnalyzer": {"main": [[{"node": "ProductSearch", "type": "main", "index": 0}]]},
            "ProductSearch": {"main": [[{"node": "ReviewAnalyzer", "type": "main", "index": 0}]]},
            "ReviewAnalyzer": {"main": [[{"node": "ReportGenerator", "type": "main", "index": 0}]]},
            "DeepSeek Report": {"ai_languageModel": [[{"node": "ReportGenerator", "type": "ai_languageModel", "index": 0}]]},
            "ReportGenerator": {"main": [[{"node": "Convert to File", "type": "main", "index": 0}]]},
        }
    else:
        base_nodes.extend(
            [
                {
                    "id": "4",
                    "name": "ProductSearch FakeStore",
                    "type": "shopmaibeli.productSearch",
                    "typeVersion": 1.0,
                    "position": [440, 100],
                    "parameters": {
                        "source": "fakestoreapi",
                        "maxResults": max_results,
                        "category": product_search_category_for(reduced_category, "fakestoreapi"),
                    },
                },
                {
                    "id": "5",
                    "name": "ProductSearch DummyJSON",
                    "type": "shopmaibeli.productSearch",
                    "typeVersion": 1.0,
                    "position": [440, 300],
                    "parameters": {
                        "source": "dummyjson",
                        "maxResults": max_results,
                        "category": product_search_category_for(reduced_category, "dummyjson"),
                    },
                },
                {
                    "id": "6",
                    "name": "ReviewAnalyzer",
                    "type": "shopmaibeli.reviewAnalyzer",
                    "typeVersion": 1.0,
                    "position": [660, 200],
                    "parameters": {},
                },
                {
                    "id": "7",
                    "name": "ReportGenerator",
                    "type": "@n8n/n8n-nodes-langchain.agent",
                    "typeVersion": 1.7,
                    "position": [880, 200],
                    "parameters": {
                        "options": {"systemMessage": REPORT_GENERATOR_SYSTEM_MESSAGE},
                        "hasOutputParser": False,
                    },
                },
                {
                    "id": "8",
                    "name": "DeepSeek Report",
                    "type": "@n8n/n8n-nodes-langchain.lmChatDeepSeek",
                    "typeVersion": 1.0,
                    "position": [880, 400],
                    "parameters": {},
                },
                {
                    "id": "9",
                    "name": "Convert to File",
                    "type": "n8n-nodes-base.convertToFile",
                    "typeVersion": 1.1,
                    "position": [1100, 200],
                    "parameters": {
                        "operation": "toText",
                        "sourceProperty": "output",
                        "options": {"fileName": f"{file_stub}_report.html"},
                    },
                },
            ]
        )
        connections = {
            "Chat Trigger": {"main": [[{"node": "QueryAnalyzer", "type": "main", "index": 0}]]},
            "DeepSeek QA": {"ai_languageModel": [[{"node": "QueryAnalyzer", "type": "ai_languageModel", "index": 0}]]},
            "QueryAnalyzer": {"main": [[
                {"node": "ProductSearch FakeStore", "type": "main", "index": 0},
                {"node": "ProductSearch DummyJSON", "type": "main", "index": 0},
            ]]},
            "ProductSearch FakeStore": {"main": [[{"node": "ReviewAnalyzer", "type": "main", "index": 0}]]},
            "ProductSearch DummyJSON": {"main": [[{"node": "ReviewAnalyzer", "type": "main", "index": 1}]]},
            "ReviewAnalyzer": {"main": [[{"node": "ReportGenerator", "type": "main", "index": 0}]]},
            "DeepSeek Report": {"ai_languageModel": [[{"node": "ReportGenerator", "type": "ai_languageModel", "index": 0}]]},
            "ReportGenerator": {"main": [[{"node": "Convert to File", "type": "main", "index": 0}]]},
        }

    return {"name": "ShopMaiBeli Shopping Workflow", "nodes": base_nodes, "connections": connections}


def has_markdown_instruction(value: Any) -> bool:
    if isinstance(value, dict):
        return any(has_markdown_instruction(item) for item in value.values())
    if isinstance(value, list):
        return any(has_markdown_instruction(item) for item in value)
    if isinstance(value, str):
        lower = value.casefold()
        return (
            ".md" in lower
            or "create a clear markdown" in lower
            or "valid markdown" in lower
            or "markdown comparison report" in lower
        )
    return False


def validate_workflow(workflow: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if set(workflow.keys()) != {"name", "nodes", "connections"}:
        errors.append("Top-level keys must be exactly: name, nodes, connections")
        return errors

    if not isinstance(workflow["nodes"], list):
        errors.append("'nodes' must be a list")
        return errors
    if not isinstance(workflow["connections"], dict):
        errors.append("'connections' must be a dict")
        return errors

    required_fields = {"id", "name", "type", "typeVersion", "position", "parameters"}
    node_names: set[str] = set()
    node_types: dict[str, str] = {}

    for index, node in enumerate(workflow["nodes"]):
        missing = required_fields.difference(node.keys())
        if missing:
            errors.append(f"Node[{index}] missing fields: {sorted(missing)}")
        if "name" in node:
            node_names.add(node["name"])
            node_types[node["name"]] = node.get("type", "")

    required_names = {
        "Chat Trigger",
        "QueryAnalyzer",
        "DeepSeek QA",
        "ReviewAnalyzer",
        "ReportGenerator",
        "DeepSeek Report",
        "Convert to File",
    }
    missing_names = required_names.difference(node_names)
    if missing_names:
        errors.append(f"Missing required nodes: {sorted(missing_names)}")

    product_search_names = [name for name, node_type in node_types.items() if node_type == "shopmaibeli.productSearch"]
    if not product_search_names:
        errors.append("At least one ProductSearch node is required")

    if any("TrustScorer" == name or "trustscorer" in name.casefold() for name in node_names):
        errors.append("TrustScorer node is not allowed")

    if has_markdown_instruction(workflow):
        errors.append("Workflow contains Markdown-oriented instructions")

    report_node = next((node for node in workflow["nodes"] if node.get("name") == "ReportGenerator"), None)
    if not report_node:
        errors.append("Missing ReportGenerator node")
    else:
        system_message = (
            report_node.get("parameters", {})
            .get("options", {})
            .get("systemMessage", "")
        )
        if "html" not in system_message.casefold():
            errors.append("ReportGenerator is not HTML-oriented")
        if (
            "create a clear markdown" in system_message.casefold()
            or "markdown comparison report" in system_message.casefold()
            or "output only valid markdown" in system_message.casefold()
        ):
            errors.append("ReportGenerator still mentions Markdown")

    convert_node = next((node for node in workflow["nodes"] if node.get("name") == "Convert to File"), None)
    if not convert_node:
        errors.append("Missing Convert to File node")
    else:
        params = convert_node.get("parameters", {})
        if params.get("operation") != "toText":
            errors.append("Convert to File operation must be 'toText'")
        if params.get("sourceProperty") != "output":
            errors.append("Convert to File sourceProperty must be 'output'")
        file_name = params.get("options", {}).get("fileName", "")
        if not str(file_name).endswith(".html"):
            errors.append("Convert to File filename must end with .html")

    for source_name, conn_map in workflow["connections"].items():
        if source_name not in node_names:
            errors.append(f"Connection source not found in nodes: {source_name}")
            continue
        if not isinstance(conn_map, dict):
            errors.append(f"Connections for {source_name} must be a dict")
            continue
        for conn_type, groups in conn_map.items():
            if not isinstance(groups, list):
                errors.append(f"Connections for {source_name}.{conn_type} must be a list")
                continue
            for group in groups:
                if not isinstance(group, list):
                    errors.append(f"Connections for {source_name}.{conn_type} inner values must be lists")
                    continue
                for conn in group:
                    target_name = conn.get("node")
                    if target_name not in node_names:
                        errors.append(f"Connection target not found in nodes: {target_name}")

    allowed_single = {
        "Chat Trigger": {"main": ("QueryAnalyzer",)},
        "DeepSeek QA": {"ai_languageModel": ("QueryAnalyzer",)},
        "QueryAnalyzer": {"main": ("ProductSearch",)},
        "ProductSearch": {"main": ("ReviewAnalyzer",)},
        "ReviewAnalyzer": {"main": ("ReportGenerator",)},
        "DeepSeek Report": {"ai_languageModel": ("ReportGenerator",)},
        "ReportGenerator": {"main": ("Convert to File",)},
    }
    allowed_dual = {
        "Chat Trigger": {"main": ("QueryAnalyzer",)},
        "DeepSeek QA": {"ai_languageModel": ("QueryAnalyzer",)},
        "QueryAnalyzer": {"main": ("ProductSearch FakeStore", "ProductSearch DummyJSON")},
        "ProductSearch FakeStore": {"main": ("ReviewAnalyzer",)},
        "ProductSearch DummyJSON": {"main": ("ReviewAnalyzer",)},
        "ReviewAnalyzer": {"main": ("ReportGenerator",)},
        "DeepSeek Report": {"ai_languageModel": ("ReportGenerator",)},
        "ReportGenerator": {"main": ("Convert to File",)},
    }

    def connection_signature() -> dict[str, dict[str, tuple[str, ...]]]:
        signature: dict[str, dict[str, tuple[str, ...]]] = {}
        for source_name, conn_map in workflow["connections"].items():
            signature[source_name] = {}
            for conn_type, groups in conn_map.items():
                flattened: list[str] = []
                for group in groups:
                    flattened.extend(conn.get("node", "") for conn in group)
                signature[source_name][conn_type] = tuple(flattened)
        return signature

    signature = connection_signature()
    if signature != allowed_single and signature != allowed_dual:
        errors.append("Connections do not match the allowed single-source or dual-source workflow patterns")

    return errors


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def print_dry_run(rows: list[dict[str, Any]], limit: int) -> None:
    print(f"[dry-run] mapped and sampled {len(rows)} rows")
    category_counts = Counter(row["reduced_category"] for row in rows)
    bucket_counts = Counter(row["specificity_bucket"] for row in rows)
    print(f"[dry-run] category counts: {dict(category_counts)}")
    print(f"[dry-run] specificity counts: {dict(bucket_counts)}")
    for row in rows[:limit]:
        print(
            "[dry-run] "
            f"category={row['reduced_category']} "
            f"bucket={row['specificity_bucket']} "
            f"score={row['specificity_score']} "
            f"query={row['query']!r}"
        )


def build_dataset(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cache_dir = Path(args.cache_dir)
    examples_path = ensure_local_file(args.examples_path, cache_dir)
    products_path = ensure_local_file(args.products_path, cache_dir)

    example_rows = load_table(
        examples_path,
        columns=[
            "query",
            "query_id",
            "query_locale",
            "split",
            "product_id",
            "esci_label",
        ],
        label="ESCI examples",
    )
    product_rows = load_table(products_path, label="ESCI products")
    product_index = build_product_index(product_rows)

    extracted = extract_examples(example_rows, product_index, args.locale, args.split)
    print(f"[stage] extracted {len(extracted)} candidate ESCI rows")

    mapped_rows: list[dict[str, Any]] = []
    skipped_counts = Counter()
    seen_queries: set[tuple[str, str, str]] = set()
    for row in extracted:
        if not args.allow_non_ascii and not is_ascii_text(normalize_text(row.get("query", ""))):
            skipped_counts["non_ascii_query"] += 1
            continue

        reduced_category, category_detail = map_category(row)
        if not reduced_category:
            skipped_counts[category_detail["reason"]] += 1
            continue

        specificity_score, specificity_bucket, specificity_detail = score_specificity(row)
        dedupe_key = (
            reduced_category,
            normalize_locale(row.get("locale", "")),
            lower_text(row.get("query")),
        )
        if dedupe_key in seen_queries:
            skipped_counts["duplicate_query"] += 1
            continue
        seen_queries.add(dedupe_key)

        enriched = dict(row)
        enriched["reduced_category"] = reduced_category
        enriched["category_mapping_detail"] = category_detail
        enriched["specificity_score"] = specificity_score
        enriched["specificity_bucket"] = specificity_bucket
        enriched["specificity_detail"] = specificity_detail
        mapped_rows.append(enriched)

    print(f"[stage] kept {len(mapped_rows)} mapped rows")
    if skipped_counts:
        print(f"[stage] skipped rows summary: {dict(skipped_counts)}")

    sampled = sample_queries(mapped_rows, args.per_category, args.seed)
    print(f"[stage] sampled {len(sampled)} rows")
    return mapped_rows, sampled


def main() -> None:
    args = parse_args()
    _, sampled_rows = build_dataset(args)

    if args.dry_run:
        print_dry_run(sampled_rows, args.dry_run_limit)
        return

    client: OpenAI | None = None
    if not args.skip_rewrite:
        openrouter_key = os.environ.get("OPENROUTER_KEY", "").strip()
        if not openrouter_key:
            raise RuntimeError("OPENROUTER_KEY is required unless --skip-rewrite is used.")
        client = build_openrouter_client(openrouter_key, args.request_timeout)

    output_rows: list[dict[str, str]] = []
    audit_rows: list[dict[str, Any]] = []
    total_rows = len(sampled_rows)

    for index, row in enumerate(sampled_rows, start=1):
        print(
            f"[progress] processing row {index}/{total_rows} "
            f"category={row['reduced_category']} "
            f"bucket={row['specificity_bucket']}"
        )
        if args.skip_rewrite:
            instruction = normalize_text(row["query"])
            llm_meta = {
                "provider": None,
                "base_url": None,
                "model": None,
                "attempts": 0,
                "mode": "skip_rewrite",
            }
        else:
            assert client is not None
            print(f"[progress] rewriting row {index}/{total_rows} via OpenRouter")
            instruction, llm_meta = rewrite_query(client, row, args.rewrite_retries)

        enriched_row = dict(row)
        enriched_row["instruction"] = instruction
        pattern = choose_workflow_pattern(enriched_row, args.workflow_pattern)

        workflow = None
        last_errors: list[str] = []
        for _ in range(2):
            candidate = build_workflow(enriched_row, pattern, args.max_results)
            last_errors = validate_workflow(candidate)
            if not last_errors:
                workflow = candidate
                break

        if workflow is None:
            print(f"[skip] row {index} failed workflow validation: {last_errors}")
            continue

        serialized_workflow = json.dumps(workflow, ensure_ascii=False, separators=(",", ":"))
        output_rows.append({"instruction": instruction, "output": serialized_workflow})
        print(
            f"[progress] completed row {index}/{total_rows} "
            f"pattern={pattern} output_rows={len(output_rows)}"
        )

        audit_rows.append(
            {
                "raw_query": row["query"],
                "rewritten_query": instruction,
                "reduced_category": row["reduced_category"],
                "specificity_bucket": row["specificity_bucket"],
                "specificity_score": row["specificity_score"],
                "workflow_pattern": pattern,
                "workflow_valid": True,
                "locale": row.get("locale", ""),
                "split": row.get("split", ""),
                "query_id": row.get("query_id", ""),
                "product_id": row.get("product_id", ""),
                "product_title": row.get("product_title", ""),
                "product_brand": row.get("product_brand", ""),
                "esci_label": row.get("esci_label", ""),
                "source_categories": row.get("source_categories", []),
                "llm": llm_meta,
            }
        )

    out_path = Path(args.out)
    write_jsonl(out_path, output_rows)
    print(f"[done] wrote {len(output_rows)} rows to {out_path}")

    audit_out = args.audit_out.strip()
    if audit_out:
        audit_path = Path(audit_out)
        write_jsonl(audit_path, audit_rows)
        print(f"[done] wrote audit rows to {audit_path}")


if __name__ == "__main__":
    main()

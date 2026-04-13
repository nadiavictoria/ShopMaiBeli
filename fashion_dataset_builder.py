"""
Build a normalized Amazon Fashion review dataset from local reviews/products CSVs.

The output schema matches the normalized Amazon review dataset used elsewhere
in the project:
    parent_asin
    product_name
    review_text
    rating
    source
    source_dataset
    brand
    verified_purchase

Typical usage:
    python fashion_dataset_builder.py \
      --reviews amazon_fashion/reviews.csv \
      --products amazon_fashion/products.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


DEFAULT_OUTPUT_DIR = Path("output")
DEFAULT_OUTPUT_JSON = DEFAULT_OUTPUT_DIR / "full_amazon_fashion_review.json"
DEFAULT_OUTPUT_CSV = DEFAULT_OUTPUT_DIR / "full_amazon_fashion_review.csv"

OUTPUT_FIELDS = [
    "parent_asin",
    "product_name",
    "review_text",
    "rating",
    "source",
    "source_dataset",
    "brand",
    "verified_purchase",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a normalized Amazon Fashion review dataset from local CSV files."
    )
    parser.add_argument("--reviews", required=True, help="Path to the local fashion reviews CSV.")
    parser.add_argument("--products", required=True, help="Path to the local fashion products CSV.")
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    return parser.parse_args()


def normalize_text(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def parse_rating(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_verified_purchase(value) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    upper = text.upper()
    if upper in {"TRUE", "FALSE"}:
        return upper.title()
    return text


def load_csv_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build_product_index(product_rows: list[dict]) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for row in product_rows:
        asin = normalize_text(row.get("asin"))
        if not asin:
            continue

        title = normalize_text(row.get("title"))
        about_item = normalize_text(row.get("about_item"))
        product_description = normalize_text(row.get("product_description"))
        brand = normalize_text(row.get("brand_name")) or normalize_text(row.get("seller_name"))

        product_name = title or about_item or product_description
        index[asin] = {
            "product_name": product_name,
            "brand": brand,
        }
    return index


def normalize_review_rows(review_rows: list[dict], product_index: dict[str, dict[str, str]]) -> list[dict]:
    normalized: list[dict] = []
    seen_keys: set[tuple[str, str]] = set()
    missing_product_rows = 0

    for row in review_rows:
        parent_asin = normalize_text(row.get("productASIN"))
        rating = parse_rating(row.get("rating"))
        review_text = normalize_text(row.get("cleaned_review_text")) or normalize_text(row.get("reviewText"))
        verified_purchase = normalize_verified_purchase(row.get("verifiedPurchase"))

        if not parent_asin or rating is None or not review_text:
            continue

        product_meta = product_index.get(parent_asin, {})
        if not product_meta:
            missing_product_rows += 1

        dedupe_key = (parent_asin, review_text[:160])
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)

        normalized.append(
            {
                "parent_asin": parent_asin,
                "product_name": product_meta.get("product_name", ""),
                "review_text": review_text,
                "rating": rating,
                "source": "Amazon_Fashion",
                "source_dataset": "local_amazon_fashion",
                "brand": product_meta.get("brand", ""),
                "verified_purchase": verified_purchase,
            }
        )

    print(f"Rows without product metadata match: {missing_product_rows}")
    return normalized


def write_outputs(rows: list[dict], output_json: Path, output_csv: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)

    with output_json.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=2)

    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    reviews_path = Path(args.reviews)
    products_path = Path(args.products)

    review_rows = load_csv_rows(reviews_path)
    product_rows = load_csv_rows(products_path)
    product_index = build_product_index(product_rows)
    normalized = normalize_review_rows(review_rows, product_index)

    write_outputs(
        normalized,
        output_json=Path(args.output_json),
        output_csv=Path(args.output_csv),
    )

    print(f"Loaded review rows: {len(review_rows)}")
    print(f"Loaded product rows: {len(product_rows)}")
    print(f"Saved normalized rows: {len(normalized)}")
    print(f"Output JSON: {args.output_json}")
    print(f"Output CSV: {args.output_csv}")
    if normalized:
        print("Sample row:")
        print(normalized[0])


if __name__ == "__main__":
    main()

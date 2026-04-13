# Full Amazon Reviews 2023 RAG builder for ShopMaiBeli.

from __future__ import annotations

import argparse
import csv
import json
import traceback
from pathlib import Path

from datasets import load_dataset
from huggingface_hub import hf_hub_download


# =========================
# SETTINGS
# =========================
HF_DATASET_REPO = "McAuley-Lab/Amazon-Reviews-2023"
TEST_CATEGORY = None  # e.g. "Electronics" for a quick single-category run
TARGET_CATEGORIES = [
    "All_Beauty",
    "Beauty_and_Personal_Care",
    "Health_and_Personal_Care",
    "Electronics",
    "Cell_Phones_and_Accessories",
]

OUTPUT_DIR = Path("output")
OUTPUT_JSON = OUTPUT_DIR / "full_amazon_review.json"
OUTPUT_CSV = OUTPUT_DIR / "full_amazon_review.csv"
DEFAULT_MAX_REVIEWS_PER_CATEGORY = 10000

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
        description="Build a normalized Amazon review corpus for selected categories."
    )
    parser.add_argument(
        "--max-reviews-per-category",
        type=int,
        default=DEFAULT_MAX_REVIEWS_PER_CATEGORY,
        help="Stop each category once this many usable review rows have been written.",
    )
    parser.add_argument(
        "--output-json",
        default=str(OUTPUT_JSON),
        help="Path to the output JSON file.",
    )
    parser.add_argument(
        "--output-csv",
        default=str(OUTPUT_CSV),
        help="Path to the output CSV file.",
    )
    return parser.parse_args()


# =========================
# HELPERS
# =========================
def load_all_categories(exclude_unknown: bool = True) -> list[str]:
    """
    Download all_categories.txt from the dataset repo and return the category names.
    """
    path = hf_hub_download(
        repo_id=HF_DATASET_REPO,
        repo_type="dataset",
        filename="all_categories.txt",
    )

    with open(path, "r", encoding="utf-8") as handle:
        categories = [line.strip() for line in handle if line.strip()]

    if exclude_unknown:
        categories = [category for category in categories if category != "Unknown"]

    return categories


def load_config(config_name: str, split: str = "full", streaming: bool = True):
    """
    Load one dataset config using the dataset's official loading script.

    Example config_name:
      raw_review_Electronics
      raw_meta_Electronics
    """
    print(f"{config_name}: loading split={split!r}, streaming={streaming}")
    return load_dataset(
        HF_DATASET_REPO,
        config_name,
        split=split,
        streaming=streaming,
        trust_remote_code=True,
    )


def _is_nonempty_text(value) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _clean_text(value) -> str:
    if not _is_nonempty_text(value):
        return ""
    return " ".join(str(value).strip().split())


def _clean_rating(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_verified_purchase(value) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if value in (None, ""):
        return ""
    return str(value)


def build_metadata_index(category: str) -> dict[str, dict[str, str]]:
    """
    Build a metadata lookup for one category:
      parent_asin -> {"product_name": ..., "brand": ...}

    We keep this in memory per category so that review rows can be enriched
    with the title/brand before writing the final corpus.
    """
    def _populate_from_rows(rows_iterable) -> tuple[dict[str, dict[str, str]], int, int]:
        metadata: dict[str, dict[str, str]] = {}
        processed = 0
        kept = 0

        for row in rows_iterable:
            processed += 1
            asin = _clean_text(row.get("parent_asin"))
            if not asin:
                continue

            title = _clean_text(row.get("title"))
            brand = _clean_text(row.get("brand")) or _clean_text(row.get("store"))
            if asin not in metadata:
                metadata[asin] = {
                    "product_name": title,
                    "brand": brand,
                }
                kept += 1
            else:
                if title and not metadata[asin]["product_name"]:
                    metadata[asin]["product_name"] = title
                if brand and not metadata[asin]["brand"]:
                    metadata[asin]["brand"] = brand

            if processed % 100000 == 0:
                print(
                    f"{category}: metadata progress processed={processed} "
                    f"unique_asins={kept}"
                )

        return metadata, processed, kept

    def _select_available_columns(dataset_obj):
        available = set(getattr(dataset_obj, "column_names", []) or [])
        wanted = ["parent_asin", "title"]
        if "brand" in available:
            wanted.append("brand")
        elif "store" in available:
            wanted.append("store")
        if hasattr(dataset_obj, "select_columns"):
            return dataset_obj.select_columns(wanted)
        return dataset_obj

    meta_config = f"raw_meta_{category}"
    try:
        meta_rows = load_config(meta_config, split="full", streaming=True)
        meta_rows = _select_available_columns(meta_rows)
        metadata, processed, kept = _populate_from_rows(meta_rows)
        print(f"{category}: metadata complete processed={processed} unique_asins={kept}")
        return metadata
    except Exception as exc:
        print(f"{category}: streaming metadata load failed, retrying non-streaming ({exc})")

    meta_rows = load_config(meta_config, split="full", streaming=False)
    meta_rows = _select_available_columns(meta_rows)
    metadata, processed, kept = _populate_from_rows(meta_rows)
    print(f"{category}: metadata complete processed={processed} unique_asins={kept}")
    return metadata


def iter_review_rows(
    category: str,
    metadata_index: dict[str, dict[str, str]],
    max_reviews: int | None = None,
):
    """
    Stream every usable review row for a category and enrich it with metadata.
    """
    review_config = f"raw_review_{category}"
    review_rows = load_config(review_config, split="full", streaming=True)
    try:
        review_rows = review_rows.select_columns(["parent_asin", "text", "rating", "verified_purchase"])
    except Exception:
        pass

    processed = 0
    yielded = 0

    for row in review_rows:
        if max_reviews is not None and yielded >= max_reviews:
            print(f"{category}: reached max_reviews_per_category={max_reviews}, stopping early")
            break

        processed += 1
        asin = _clean_text(row.get("parent_asin"))
        review_text = _clean_text(row.get("text"))
        rating = _clean_rating(row.get("rating"))

        if not asin or not review_text or rating is None:
            continue

        metadata = metadata_index.get(asin, {})
        yield {
            "parent_asin": asin,
            "product_name": metadata.get("product_name", ""),
            "review_text": review_text,
            "rating": rating,
            "source": category,
            "source_dataset": HF_DATASET_REPO,
            "brand": metadata.get("brand", ""),
            "verified_purchase": _clean_verified_purchase(row.get("verified_purchase")),
        }
        yielded += 1

        if processed % 100000 == 0:
            print(
                f"{category}: review progress processed={processed} "
                f"written={yielded}"
            )

    print(f"{category}: review complete processed={processed} written={yielded}")


def write_dataset(
    categories: list[str],
    output_json_path: Path,
    output_csv_path: Path,
    max_reviews_per_category: int,
) -> tuple[int, list[str]]:
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_csv_path.parent.mkdir(parents=True, exist_ok=True)

    total_rows = 0
    failed_categories: list[str] = []

    with open(output_json_path, "w", encoding="utf-8") as json_handle, open(
        output_csv_path, "w", encoding="utf-8", newline=""
    ) as csv_handle:
        writer = csv.DictWriter(csv_handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()

        json_handle.write("[\n")
        first_row = True

        for category in categories:
            try:
                print(f"\nLoading category: {category}")
                metadata_index = build_metadata_index(category)

                category_rows = 0
                for output_row in iter_review_rows(
                    category,
                    metadata_index,
                    max_reviews=max_reviews_per_category,
                ):
                    writer.writerow(output_row)
                    if not first_row:
                        json_handle.write(",\n")
                    json.dump(output_row, json_handle, ensure_ascii=False)
                    first_row = False
                    total_rows += 1
                    category_rows += 1

                    if category_rows % 100000 == 0:
                        print(f"{category}: flushed {category_rows} rows to output")

                print(f"{category}: finished with {category_rows} output rows")
            except Exception as exc:
                print(f"Error in {category}: {exc}")
                traceback.print_exc()
                failed_categories.append(category)

        json_handle.write("\n]\n")

    return total_rows, failed_categories


def build_dataset() -> None:
    args = parse_args()
    categories = load_all_categories(exclude_unknown=True)
    print(f"Loaded {len(categories)} categories")

    if TEST_CATEGORY:
        categories = [category for category in categories if category == TEST_CATEGORY]
        if not categories:
            raise ValueError(f"TEST_CATEGORY={TEST_CATEGORY!r} not found in all_categories.txt")
        print(f"Testing only category: {TEST_CATEGORY}")
    elif TARGET_CATEGORIES:
        categories = [category for category in categories if category in TARGET_CATEGORIES]
        print(f"Using target categories ({len(categories)}): {categories}")

    if not categories:
        raise RuntimeError("No categories selected.")

    output_json_path = Path(args.output_json)
    output_csv_path = Path(args.output_csv)
    total_rows, failed_categories = write_dataset(
        categories,
        output_json_path=output_json_path,
        output_csv_path=output_csv_path,
        max_reviews_per_category=args.max_reviews_per_category,
    )

    print("\nDone.")
    print(f"Saved CSV:  {output_csv_path}")
    print(f"Saved JSON: {output_json_path}")
    print(f"Total rows saved: {total_rows}")

    if failed_categories:
        print(f"\nFailed categories ({len(failed_categories)}):")
        for category in failed_categories:
            print(f" - {category}")


if __name__ == "__main__":
    build_dataset()

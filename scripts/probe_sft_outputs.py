"""
Probe the served ShopMaiBeli SFT model with held-out queries and save raw outputs.

This script intentionally inspects the raw assistant text before any backend JSON
cleanup. It is useful for catching issues such as:
- extra prose before the JSON object
- markdown fences
- repetition of the user instruction
- malformed or truncated JSON

Usage:
    python scripts/probe_sft_outputs.py

    python scripts/probe_sft_outputs.py \
        --base-url http://localhost:8001 \
        --output output/sft_probe_results.jsonl

    python scripts/probe_sft_outputs.py \
        --queries-file output/heldout_queries.txt
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


DEFAULT_QUERIES = [
    "find me a gaming mouse under $60 with strong reviews",
    "show me a women's black handbag for work under $120",
    "best sunscreen for sensitive skin under $25",
    "recommend a mechanical keyboard for coding under $100",
    "need a travel backpack that fits a laptop under $80",
    "compare a few office chairs for back support under $200",
    "show me affordable noise cancelling headphones for flights",
    "recommend a lightweight moisturizer for acne-prone skin",
    "find me a men's running shoe for wide feet under $90",
    "best webcam for online meetings under $70",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe raw outputs from the served ShopMaiBeli SFT model")
    parser.add_argument("--base-url", default="http://localhost:8001", help="Base URL of the OpenAI-compatible SFT server")
    parser.add_argument("--model", default="shopmaibeli-sft", help="Model name registered in the vLLM server")
    parser.add_argument(
        "--system-prompt-file",
        default="models/prompts/workflow_gen_sft.txt",
        help="System prompt file used for generation",
    )
    parser.add_argument(
        "--queries-file",
        default="output/heldout_sft_queries.txt",
        help="Optional newline-delimited query file. Defaults to the checked-in held-out set.",
    )
    parser.add_argument(
        "--output",
        default="output/sft_probe_results.jsonl",
        help="Where to save raw generations and diagnostics",
    )
    parser.add_argument("--temperature", type=float, default=0.1, help="Sampling temperature")
    parser.add_argument("--max-tokens", type=int, default=768, help="Maximum output tokens")
    return parser.parse_args()


def load_queries(path: str | None) -> list[str]:
    if not path:
        return list(DEFAULT_QUERIES)

    query_path = Path(path)
    return [
        line.strip()
        for line in query_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_system_prompt(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def analyze_raw_output(query: str, raw: str) -> dict:
    raw = raw or ""
    stripped = raw.strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    leading = stripped[:start].strip() if start != -1 else stripped
    trailing = stripped[end + 1 :].strip() if end != -1 else ""

    contains_json_object = start != -1 and end != -1 and end >= start
    starts_with_brace = stripped.startswith("{")
    contains_user_prefix = "User wants to:" in raw
    contains_markdown_fence = "```" in raw
    contains_explanatory_prefix = bool(
        re.search(r"(here(?:'s| is)|workflow json|below is|certainly|sure)", leading, re.IGNORECASE)
    )

    parsed_ok = False
    parse_error = None
    if contains_json_object:
        candidate = stripped[start : end + 1]
        try:
            json.loads(candidate)
            parsed_ok = True
        except json.JSONDecodeError as exc:
            parse_error = str(exc)

    return {
        "query": query,
        "raw_output": raw,
        "starts_with_brace": starts_with_brace,
        "contains_json_object": contains_json_object,
        "contains_user_prefix": contains_user_prefix,
        "contains_markdown_fence": contains_markdown_fence,
        "contains_explanatory_prefix": contains_explanatory_prefix,
        "leading_text": leading,
        "trailing_text": trailing,
        "parsed_ok": parsed_ok,
        "parse_error": parse_error,
    }


def main() -> None:
    args = parse_args()
    from openai import OpenAI

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    queries = load_queries(args.queries_file)
    system_prompt = load_system_prompt(args.system_prompt_file)
    client = OpenAI(api_key="EMPTY", base_url=args.base_url.rstrip("/") + "/v1")

    print(f"[probe] sending {len(queries)} query(s) to {args.base_url}")
    print(f"[probe] writing results to {output_path}")

    results = []
    for idx, query in enumerate(queries, 1):
        print(f"[probe] {idx}/{len(queries)} {query}")
        response = client.chat.completions.create(
            model=args.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
        raw = response.choices[0].message.content or ""
        result = analyze_raw_output(query, raw)
        results.append(result)

    with output_path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")

    print("\n[probe] summary")
    for key in (
        "starts_with_brace",
        "contains_user_prefix",
        "contains_markdown_fence",
        "contains_explanatory_prefix",
        "parsed_ok",
    ):
        count = sum(1 for item in results if item[key])
        print(f"  {key}: {count}/{len(results)}")

    print("\n[probe] suspicious outputs")
    suspicious = [
        item for item in results
        if not item["starts_with_brace"]
        or item["contains_user_prefix"]
        or item["contains_markdown_fence"]
        or item["contains_explanatory_prefix"]
        or not item["parsed_ok"]
    ]
    if not suspicious:
        print("  none")
        return

    for item in suspicious:
        print(f"  - {item['query']}")
        if item["leading_text"]:
            print(f"    leading_text={item['leading_text'][:120]!r}")
        if item["trailing_text"]:
            print(f"    trailing_text={item['trailing_text'][:120]!r}")
        if item["parse_error"]:
            print(f"    parse_error={item['parse_error']}")


if __name__ == "__main__":
    main()

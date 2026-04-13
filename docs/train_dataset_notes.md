# Train Dataset Notes

This note summarizes how the final SFT training dataset was created for ShopMaiBeli and what files were kept after cleanup.

## Goal

The goal was to build a small but clean supervised fine-tuning dataset for workflow generation.

Each training example follows this format:

```json
{"instruction":"...","output":"{...workflow json...}"}
```

The `instruction` is a natural-language shopping request.
The `output` is a JSON-encoded ShopMaiBeli workflow.

## Source Data

Two main sources were used:

1. ESCI shopping queries dataset
2. Curated project-specific workflow prompts already aligned with ShopMaiBeli

The ESCI dataset was used to provide realistic user query phrasing.
The project-specific prompts were used to preserve stronger examples of the workflow style we actually want the model to learn.

## Category Alignment

The query dataset was restricted to the same project-relevant category set used in the Amazon Reviews RAG builder:

- `beauty_personal_care`
- `electronics_mobile`
- `fashion`
- `home_kitchen`
- `groceries`
- `automotive`
- `sports_outdoors`
- `office_school`
- `baby_kids`
- `pets`
- `tools_home_improvement`

This kept the train set aligned with the product/review domains actually used by the rest of the system.

## Current Retained Files

After cleanup, the relevant train-dataset files are:

- `build_train_esci.py`
- `rewrite_train_esci_queries.py`
- `convert_rewritten_to_train_jsonl.py`
- `data/workflows/train_esci_queries.jsonl`
- `data/workflows/train_esci_queries_rewritten.jsonl`
- `data/workflows/train_populated.jsonl`
- `data/workflows/train_final.jsonl`

Older one-off cleanup scripts and redundant intermediate train files were removed to keep the repo easier to follow.

## Build Pipeline

The dataset was created in several stages.

### 1. Extract ESCI Queries

Script:

- `build_train_esci.py`

What it did:

- loaded ESCI parquet files
- extracted raw queries and metadata
- mapped each query into the reduced ShopMaiBeli category system
- wrote an intermediate JSONL file

Intermediate output:

- `data/workflows/train_esci_queries.jsonl`

### 2. Rewrite Queries Into Natural User Requests

Script:

- `rewrite_train_esci_queries.py`

What it did:

- filtered noisy or obviously mismatched rows
- rewrote raw ESCI queries into more natural shopping-assistant prompts
- reduced over-specific wording where possible

Rewritten output:

- `data/workflows/train_esci_queries_rewritten.jsonl`

### 3. Convert Rewritten Queries Into Train Format

Script:

- `convert_rewritten_to_train_jsonl.py`

What it did:

- converted rewritten queries into `instruction` / `output` pairs
- generated valid workflow JSON for each query
- validated the workflow structure

What it produced during the build process:

- a train-format ESCI-derived workflow dataset used as one source for later refinement

## Additional Prompt Expansion

An extra populated dataset was generated with ChatGPT-based variation.

Main retained file:

- `data/workflows/train_populated.jsonl`

This expansion increased variety, but it also introduced many low-quality mechanical variants such as malformed prefix stacking.

Examples of bad generated forms:

- `need Recommend ...`
- `show me Compare ...`
- `any good some ...`

Because of that, the populated file was not used directly.
Instead, only the cleaner and more useful variations were selectively retained for the final dataset.

## Merge Strategy

Instead of replacing the core dataset with the populated one, a selective merge was used.

Reason:

- the small curated set had better prompt quality
- the populated set had more coverage but also more noise

Approach:

- keep the clean core examples
- add only the better extra rows from the cleaned populated set
- remove near-duplicates
- prefer more natural phrasing where multiple variants existed

In practice, this meant:

- keeping the strongest manually curated prompts
- using ESCI-derived prompts for realism
- selectively keeping only the best extra variations from the populated set
- dropping malformed, redundant, and overly specific variants

## Final Dataset

Final training file:

- `data/workflows/train_final.jsonl`

Final properties:

- 73 examples
- valid `instruction` / `output` structure
- workflow JSON validated successfully
- cleaner and more natural than the larger automatically populated dataset
- intended to be the main file for an initial SFT run

## Why The Final Dataset Is Small

The dataset was intentionally reduced during cleanup because quality was prioritized over quantity.

The main issues that caused examples to be removed were:

- category mismatches
- awkward or template-like query phrasing
- over-specific brand/model references
- near-duplicate prompt variants

This means the final file is safer for an initial SFT run, even though it is smaller.

## Limitations

The final dataset is still relatively small for SFT.

Main limitations:

- limited size
- some category coverage is thinner than others
- some prompts are still more product-specific than ideal
- workflow outputs are template-generated rather than hand-authored one by one

Because of this, the final dataset should be viewed as a clean first training set rather than a final long-term production dataset.

## Cleanup Summary

The ESCI-related workspace was cleaned up after the final dataset was produced.

Removed during cleanup:

- redundant intermediate train-format files that were no longer needed
- one-off cleanup scripts used only during iterative experimentation
- obsolete prompt-planning notes

Kept after cleanup:

- the raw ESCI-derived intermediate query file
- the rewritten ESCI query file
- the ChatGPT-populated variation file
- the final curated SFT training file
- the core scripts still needed to reproduce the main steps

## Suggested Report Framing

For the report, this process can be described as:

1. Start from real shopping queries using ESCI
2. Align query categories with the project's Amazon Reviews RAG domains
3. Rewrite and filter queries into natural shopping-assistant prompts
4. Generate valid workflow targets in the ShopMaiBeli schema
5. Remove noisy synthetic variants and keep a smaller high-quality final set

This framing highlights that the dataset was built with both realism and schema alignment in mind, while also acknowledging that data cleaning was necessary to improve training quality.

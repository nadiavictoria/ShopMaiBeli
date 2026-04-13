# RAG Dataset Notes

This note summarizes how the RAG dataset subset was built for ShopMaiBeli.

## Goal

The goal was to create a compact review-backed product dataset for retrieval and downstream shopping analysis.

The builder does not try to download the full Amazon Reviews 2023 corpus into local storage.
Instead, it samples a manageable subset of products and one representative review per product from selected categories.

## Source Data

The final RAG plan uses a hybrid source setup:

1. Amazon Reviews 2023 from McAuley Lab for:
   - `Beauty_and_Personal_Care`
   - `Electronics`
   - `Cell_Phones_and_Accessories`
2. A separate Kaggle fashion reviews dataset for fashion coverage

Relevant builder scripts:

- [dataset_builder.py](../dataset_builder.py)
- [fashion_dataset_builder.py](../fashion_dataset_builder.py)

Primary Amazon Reviews repo used by the script:

- `McAuley-Lab/Amazon-Reviews-2023`

## Why A Subset Was Needed

The full Amazon Reviews 2023 dataset is very large.

Using the full dataset directly would be expensive and slow for this project because:

- there are many categories that are not relevant to the shopping assistant scope
- loading all review and metadata splits would take too long
- the project only needs enough product/review coverage to support retrieval and comparison workflows

Because of that, the builder uses a category-restricted sampling strategy.

## Category Selection

The RAG dataset was narrowed to the most important project-facing domains:

- beauty / personal care
- electronics
- cell phones / accessories
- fashion

The original attempt used a wider Amazon Reviews category set, but some categories were too large to process efficiently for this project timeline.

In particular, very large categories such as `Home_and_Kitchen` and `Clothing_Shoes_and_Jewelry` created major runtime and download costs.

Because fashion was still important, it was moved to a separate Kaggle-based ingestion path instead of relying on the very large McAuley fashion-related category.

## Builder Logic

The current RAG pipeline has two ingestion paths.

### A. McAuley Lab Builder

The Amazon Reviews builder works category by category for the three retained McAuley categories.

#### 1. Load Category List

The script first downloads `all_categories.txt` from the dataset repo and filters out `Unknown`.

It then narrows the working set to:

- `Beauty_and_Personal_Care`
- `Electronics`
- `Cell_Phones_and_Accessories`

#### 2. Sample Candidate Products From Metadata

For each category:

- the script loads the metadata split `raw_meta_<category>`
- it keeps only `parent_asin` and `title`
- it reservoir-samples candidate products

This step avoids loading the entire category into memory unnecessarily.

The script oversamples metadata candidates because not every product will later have a usable review row.

#### 3. Collect Representative Reviews

For each category:

- the script loads the review split `raw_review_<category>`
- it keeps only `parent_asin`, `text`, and `rating`
- it looks for sampled ASINs from the metadata stage
- it keeps one usable review per distinct sampled product

This means each saved row corresponds to a distinct product rather than many reviews from the same item.

#### 4. Write Output Files

The builder writes:

- `output/amazon_reviews_sample.json`
- `output/amazon_reviews_sample.csv`

Each row includes:

- `parent_asin`
- `product_name`
- `review_text`
- `rating`
- `source`

### B. Fashion Kaggle Builder

The fashion domain is handled separately using:

- [fashion_dataset_builder.py](../fashion_dataset_builder.py)

This builder:

- reads a local CSV or JSONL fashion reviews file
- maps different possible column names into a shared schema
- keeps review text, rating, product name, optional product ID, optional brand, and source tags
- writes normalized JSON and CSV outputs

Output files:

- `output/fashion_reviews_sample.json`
- `output/fashion_reviews_sample.csv`

This makes it possible to keep fashion in the RAG dataset without downloading and processing the very large McAuley clothing split.

## Append Behavior

The builder was later updated so reruns can add more products instead of replacing the whole dataset.

Current behavior:

- if an existing output JSON file is present, it is loaded first
- existing rows are indexed by `source + parent_asin`
- reruns skip already collected products
- new rows are appended and deduplicated before writing output again

This makes the builder more practical for iterative expansion.

## Practical Advantages Of This Design

This hybrid design has a few benefits:

- keeps runtime manageable by restricting the heavy McAuley categories
- preserves strong coverage for core electronics and beauty domains
- keeps fashion in scope through a lighter alternative source
- avoids collecting many duplicate reviews for the same product
- supports incremental dataset growth
- produces both JSON and CSV outputs for inspection and downstream use

## Limitations

The RAG dataset subset is useful, but it is still only a sampled approximation of the full product/review space.

Main limitations:

- only selected categories are included
- only one representative review is kept per sampled product
- some useful long-tail products may be missed due to sampling
- product coverage depends on available metadata and matching usable reviews
- the hybrid fashion source may not have exactly the same schema richness as the McAuley categories

This means the dataset is suitable for a prototype or project-scale RAG setup, but not equivalent to full-corpus coverage.

## Relationship To The Train Dataset

The RAG dataset builder and the train dataset builder are related but separate.

RAG builder:

- based on Amazon Reviews 2023 for beauty/electronics/mobile
- supplemented with a separate fashion reviews dataset
- used for retrieval and product/review grounding

Train dataset builder:

- based mainly on ESCI shopping queries plus workflow generation logic
- used for supervised fine-tuning of workflow generation

The two were aligned through category selection so that the shopping intents used for training stay close to the domains actually supported by the RAG data.

## Suggested Report Framing

For the report, the RAG dataset creation can be described as:

1. Keep the most important shopping domains for the project
2. Use McAuley Lab Amazon Reviews 2023 where category-specific review and metadata support is strongest
3. Supplement fashion with a smaller dedicated dataset to avoid very large category downloads
4. Sample candidate products and one representative review per product
5. Save a compact structured subset for downstream retrieval and product comparison

This framing highlights the key tradeoff: the project uses a smaller but targeted and tractable subset rather than the full raw corpus.

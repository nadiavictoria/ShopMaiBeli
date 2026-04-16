"""
Workflow generation logic for ShopMaiBeli.

Generation chain (first success wins):
  1. SFT model via vLLM (SFT_MODEL_URL env var)
  2. DeepSeek API fallback (DEEPSEEK_API_KEY env var)
  3. Hardcoded example_shopping.json fallback

Usage:
    from backend.workflow_generator import generate_workflow
    workflow = generate_workflow(payload)
"""

import json
import logging
import os
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_QUERY_ANALYZER_SYSTEM_MESSAGE = (
    "You are a shopping query analyzer for a shopping assistant. "
    "Interpret the user's request and output ONLY valid JSON with these keys: "
    "product_type (string), "
    "product_category (string or null), "
    "closest_catalog_category (string or null), "
    "category_confidence (number from 0.0 to 1.0), "
    "search_terms (array of 1 to 5 strings, ordered best-first), "
    "budget (number or null), "
    "priorities (array of strings), "
    "preferred_brands (array of strings). "
    "Use closest_catalog_category only if it is a strong fit for the available catalog. "
    "If no catalog category is a good fit, set closest_catalog_category to null and lower "
    "category_confidence. Keep search_terms practical and retrieval-friendly."
)

# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "prompts", "workflow_gen.txt")
_SFT_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "prompts", "workflow_gen_sft.txt")
_FALLBACK_WORKFLOW_PATH = os.path.join(os.path.dirname(__file__), "..", "workflows", "example_shopping.json")
_SFT_DEBUG_DIR = os.path.join(os.path.dirname(__file__), "..", "artifacts", "sft_debug")


def _load_system_prompt(path: str = _PROMPT_PATH) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning("%s not found, using minimal prompt", os.path.basename(path))
        return (
            "You are a workflow generator. Given a shopping query, output a valid "
            "n8n Workflow JSON object. Output ONLY JSON — no markdown, no explanation."
        )


def _load_fallback_workflow() -> dict:
    with open(_FALLBACK_WORKFLOW_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_sft_debug_artifact(raw_text: str) -> None:
    """Persist the latest raw SFT response for debugging malformed outputs."""
    try:
        os.makedirs(_SFT_DEBUG_DIR, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        latest_path = os.path.join(_SFT_DEBUG_DIR, "latest_raw_response.txt")
        timestamped_path = os.path.join(_SFT_DEBUG_DIR, f"{timestamp}_raw_response.txt")
        for path in (latest_path, timestamped_path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(raw_text or "")
    except Exception as exc:
        logger.warning("[_write_sft_debug_artifact] failed to persist raw SFT output: %s", exc)


# ---------------------------------------------------------------------------
# Query extraction
# ---------------------------------------------------------------------------

def extract_latest_query(chat_history: list) -> str:
    """Return the last user message from chat_history, or empty string."""
    for msg in reversed(chat_history):
        if isinstance(msg, dict):
            role = msg.get("role", "") or msg.get("type", "")
            if role in ("user", "human"):
                content = msg.get("content") or msg.get("output") or ""
                if content:
                    return str(content).strip()
    return ""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_workflow(workflow: dict) -> list[str]:
    """
    Validate a workflow dict. Returns a list of error strings (empty = valid).
    """
    errors = []

    if "name" not in workflow:
        errors.append("Missing 'name'")

    if "nodes" not in workflow:
        errors.append("Missing 'nodes'")
        return errors

    if not isinstance(workflow["nodes"], list):
        errors.append("'nodes' must be a list")
        return errors

    if "connections" not in workflow:
        errors.append("Missing 'connections'")

    node_names: set[str] = set()
    for i, node in enumerate(workflow["nodes"]):
        for required in ("id", "name", "type", "typeVersion", "position"):
            if required not in node:
                errors.append(f"Node[{i}] missing required field '{required}'")
        if "name" in node:
            node_names.add(node["name"])

    node_types = [
        n.get("type", "").split(".")[-1]
        for n in workflow.get("nodes", [])
    ]
    if "chatTrigger" not in node_types:
        errors.append("No chatTrigger node found")

    for source, conns in workflow.get("connections", {}).items():
        if source not in node_names:
            errors.append(f"Connection source '{source}' does not match any node name")
        if not isinstance(conns, dict):
            errors.append(f"Connections for '{source}' must be a dict")
            continue
        for conn_type, outputs in conns.items():
            if not isinstance(outputs, list):
                errors.append(f"Connection '{source}.{conn_type}' outputs must be a list")
                continue
            for output_list in outputs:
                if not isinstance(output_list, list):
                    errors.append(f"Connection '{source}.{conn_type}' inner list must be a list")
                    continue
                for conn in output_list:
                    if "node" not in conn:
                        errors.append(f"Connection in '{source}.{conn_type}' missing 'node' key")
                    elif conn["node"] not in node_names:
                        errors.append(f"Connection target '{conn['node']}' does not match any node name")

    return errors


def _normalize_report_output(workflow: dict) -> dict:
    """
    Normalize generated workflows to the frontend's current Markdown-first UX.

    Older prompts/training examples may emit HTML-focused report generators and
    `.html` file targets. We rewrite those to Markdown so the Chainlit frontend
    can display the final report cleanly without raw HTML leakage.
    """
    nodes = workflow.get("nodes", [])
    if len(nodes) == 1 and isinstance(nodes[0], list):
        logger.info("[_normalize_report_output] flattening nested nodes array from generated workflow")
        nodes = nodes[0]
        workflow["nodes"] = nodes

    for node in nodes:
        node_type = node.get("type", "")
        node_name = node.get("name", "")
        parameters = node.setdefault("parameters", {})

        if node_type.endswith(".agent") and node_name == "ReportGenerator":
            options = parameters.setdefault("options", {})
            system_message = options.get("systemMessage", "")
            if "HTML" in system_message or "html" in system_message:
                options["systemMessage"] = (
                    "You are a shopping report generator for a shopping assistant. "
                    "You will receive a list of real products fetched from a product API, "
                    "along with their prices, ratings, and review sentiments. "
                    "Using ONLY the products provided in the input data, create a clear "
                    "Markdown comparison report. Include: a short summary header naming "
                    "the category/query, a ranked product table (columns: Rank, Name, "
                    "Price, Rating, Sentiment), and a brief justification for the top pick. "
                    "If the exact brand requested is not in the data, note that and "
                    "recommend the best available alternatives. Output ONLY valid Markdown "
                    "— no HTML, no code blocks, no explanation."
                )

        if node_type.endswith(".agent") and node_name == "QueryAnalyzer":
            options = parameters.setdefault("options", {})
            options["systemMessage"] = _QUERY_ANALYZER_SYSTEM_MESSAGE

        if node_type == "n8n-nodes-base.convertToFile":
            options = parameters.setdefault("options", {})
            file_name = options.get("fileName", "")
            if file_name.endswith(".html"):
                options["fileName"] = file_name[:-5] + ".md"

        if node_type == "shopmaibeli.productSearch":
            source = parameters.get("source", "")
            if source == "dummy_store":
                parameters["source"] = "dummyjson"
            elif source == "fakestore":
                parameters["source"] = "fakestoreapi"

    return workflow




# ---------------------------------------------------------------------------
# JSON extraction from LLM output
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    """
    Extract the first JSON object from LLM output.
    Handles markdown fences (```json ... ```) and stray text.
    """
    # Strip markdown fences
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()

    repaired_text = text
    # Common malformed SFT pattern: "nodes": [[ ... ]], should be a single list.
    repaired_text = repaired_text.replace('"nodes": [[', '"nodes": [')
    repaired_text = repaired_text.replace(']], "connections"', '], "connections"')
    repaired_text = repaired_text.replace(']], "settings"', '], "settings"')
    repaired_text = repaired_text.replace(']], "meta"', '], "meta"')
    if repaired_text != text:
        logger.info("[_extract_json] applied common JSON repair rules to model output")
        text = repaired_text

    # Try to parse the whole thing first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find the outermost {...} block
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in LLM response")

    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])

    raise ValueError("Unterminated JSON object in LLM response")


# ---------------------------------------------------------------------------
# Model calls
# ---------------------------------------------------------------------------

def _call_sft_model(user_query: str) -> dict:
    """
    Call the fine-tuned Qwen2.5-3B model served via vLLM.
    Requires SFT_MODEL_URL env var (e.g. http://vast-ai-host:8000).
    """
    from openai import OpenAI

    base_url = os.environ["SFT_MODEL_URL"].rstrip("/") + "/v1"
    client = OpenAI(api_key="EMPTY", base_url=base_url)

    system_prompt = _load_system_prompt(_SFT_PROMPT_PATH)
    response = client.chat.completions.create(
        model="shopmaibeli-sft",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query},
        ],
        temperature=0.1,
        max_tokens=1400,
    )
    raw = response.choices[0].message.content
    logger.info("[_call_sft_model] raw response length=%s", len(raw) if raw else 0)
    if raw:
        logger.info("[_call_sft_model] raw response preview=%r", raw[:400])
        _write_sft_debug_artifact(raw)
    return _extract_json(raw)


def _call_deepseek_fallback(user_query: str) -> dict:
    """
    Call DeepSeek API as fallback workflow generator.
    Requires DEEPSEEK_API_KEY env var.
    """
    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com/v1",
    )

    system_prompt = _load_system_prompt(_PROMPT_PATH)
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"User wants to: {user_query}"},
        ],
        temperature=0.1,
        max_tokens=2048,
    )
    raw = response.choices[0].message.content
    return _extract_json(raw)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_workflow(payload: dict) -> dict:
    """
    Generate an n8n Workflow JSON from the user's latest message.

    Falls back gracefully:
      SFT model → DeepSeek → example_shopping.json
    """
    chat_history = payload.get("chat_history", [])
    user_query = extract_latest_query(chat_history)

    if not user_query:
        logger.info("[generate_workflow] No user query found, using fallback workflow")
        return _load_fallback_workflow()

    logger.info(f"[generate_workflow] Generating workflow for: {user_query!r}")

    # 1. Try SFT model
    if os.environ.get("SFT_MODEL_URL"):
        try:
            workflow = _call_sft_model(user_query)
            workflow = _normalize_report_output(workflow)
            errors = validate_workflow(workflow)
            if not errors:
                logger.info("[generate_workflow] SFT model succeeded")
                return workflow
            logger.warning(f"[generate_workflow] SFT model returned invalid workflow: {errors}")
        except Exception as e:
            logger.warning(f"[generate_workflow] SFT model failed: {e}")

    # 2. Try DeepSeek fallback
    if os.environ.get("DEEPSEEK_API_KEY"):
        try:
            workflow = _call_deepseek_fallback(user_query)
            workflow = _normalize_report_output(workflow)
            errors = validate_workflow(workflow)
            if not errors:
                logger.info("[generate_workflow] DeepSeek fallback succeeded")
                return workflow
            logger.warning(f"[generate_workflow] DeepSeek returned invalid workflow: {errors}")
        except Exception as e:
            logger.warning(f"[generate_workflow] DeepSeek fallback failed: {e}")

    # 3. Final fallback
    logger.info("[generate_workflow] Using hardcoded fallback workflow")
    return _normalize_report_output(_load_fallback_workflow())

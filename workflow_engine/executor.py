"""
WorkflowExecutor - the main execution engine for workflows.

Executes workflow nodes in parallel where possible, with retry logic.
"""

import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, List, Optional, Tuple

from .models import NodeNotification, NodeOutput
from .workflow import Workflow
from .context import ExecutionContext
# get_executor_class imported lazily inside methods to avoid circular import

logger = logging.getLogger(__name__)


def _format_results(last_data: dict) -> str:
    """
    Format the last node's output into human-readable markdown.

    Handles:
    - products list (from ProductSearch / ReviewAnalyzer)
    - generic key-value output as a fallback
    """
    # If the final node stored a report (Markdown or text), surface it directly
    output_text = last_data.get("output", "")
    if output_text and not output_text.strip().startswith("<!"):
        return output_text

    products = last_data.get("products")

    if products and isinstance(products, list):
        lines = [f"## 🛍️ Found {len(products)} Product(s)\n"]
        for i, p in enumerate(products, 1):
            name = p.get("name", "Unknown")
            price = p.get("price", "N/A")
            rating = p.get("rating", "N/A")
            source = p.get("source", "")
            description = p.get("description", "")

            # Truncate long descriptions
            if description and len(description) > 100:
                description = description[:97] + "..."

            lines.append(f"### {i}. {name}")
            lines.append(f"- **Price:** ${price}")
            lines.append(f"- **Rating:** {rating} ⭐")

            # Show review analysis fields if ReviewAnalyzer ran
            sentiment = p.get("review_sentiment")
            if sentiment:
                confidence = p.get("review_confidence", 0)
                summary = p.get("review_summary", "")
                sentiment_icon = {"positive": "😊", "neutral": "😐", "negative": "😞"}.get(sentiment, "")
                lines.append(f"- **Sentiment:** {sentiment_icon} {sentiment} ({confidence:.0%} confidence)")
                if summary:
                    lines.append(f"- **Review:** {summary}")

            if description:
                lines.append(f"- **Description:** {description}")
            if source:
                lines.append(f"- **Source:** `{source}`")
            lines.append("")  # blank line between products

        return "\n".join(lines)

    # Fallback: show non-empty string values from the output dict (skip html — rendered separately)
    if last_data:
        lines = []
        for k, v in last_data.items():
            if k == "html":
                continue
            if isinstance(v, str) and v:
                lines.append(f"**{k}:** {v}")
        return "\n".join(lines)

    return ""


class WorkflowExecutor:
    """
    Main execution engine for n8n workflows.

    This class orchestrates the execution of a workflow by:
    1. Loading and parsing the workflow JSON
    2. Determining execution order (topological sort)
    3. Grouping independent nodes into parallel execution levels
    4. Executing each level (parallel where possible) with retry logic
    5. Managing data flow between nodes via ExecutionContext
    6. Managing session contexts internally
    """

    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 2, 4]  # exponential backoff in seconds

    def __init__(self, workflow: Workflow):
        self.workflow = workflow
        # Session contexts storage: session_id -> ExecutionContext
        self._contexts: Dict[str, ExecutionContext] = {}

    @classmethod
    def from_json(cls, workflow_json: dict) -> "WorkflowExecutor":
        """Create executor from workflow JSON dict."""
        workflow = Workflow(workflow_json)
        return cls(workflow)

    @classmethod
    def from_file(cls, file_path: str) -> "WorkflowExecutor":
        """Create executor from workflow JSON file."""
        with open(file_path, "r", encoding="utf-8") as f:
            workflow_json = json.load(f)
        return cls.from_json(workflow_json)

    def get_context(self, session_id: str) -> ExecutionContext:
        """Get or create an ExecutionContext for the given session_id."""
        if session_id not in self._contexts:
            self._contexts[session_id] = ExecutionContext(session_id=session_id)
        return self._contexts[session_id]

    def clear_context(self, session_id: str):
        """Clear the ExecutionContext for the given session_id."""
        if session_id in self._contexts:
            del self._contexts[session_id]

    @staticmethod
    def _get_executor_class(node_type: str):
        """
        Lazy import of get_executor_class to avoid circular imports.
        (nodes → workflow_engine.models, workflow_engine → nodes)
        """
        from nodes import get_executor_class  # noqa: PLC0415
        return get_executor_class(node_type)

    # ------------------------------------------------------------------
    # Change 1: Parallel execution levels
    # ------------------------------------------------------------------

    def _get_execution_levels(self, execution_order: List[str]) -> List[List[str]]:
        """
        Group topologically sorted nodes into parallel execution levels.

        Nodes at the same level have no dependencies on each other and can
        run concurrently via asyncio.gather(). Nodes at level N all depend
        only on nodes at levels 0..N-1.

        Example:
            Trigger → [SearchA, SearchB] → ReviewAnalyzer → Output
            Level 0: [Trigger]
            Level 1: [SearchA, SearchB]   ← run in parallel
            Level 2: [ReviewAnalyzer]
            Level 3: [Output]

        Args:
            execution_order: Flat topological order from workflow.get_execution_order()

        Returns:
            List of levels; each level is a list of node names.
        """
        if not execution_order:
            return []

        order_set = set(execution_order)
        placed: set = set()
        levels: List[List[str]] = []

        while len(placed) < len(execution_order):
            current_level = []
            for node_name in execution_order:
                if node_name in placed:
                    continue
                # A node can execute at this level if ALL its main-flow
                # parents have already been placed in a previous level.
                parents = self.workflow.get_parent_nodes(node_name)
                # Only consider parents that are part of the main flow
                main_parents = [p for p in parents if p in order_set]
                if all(p in placed for p in main_parents):
                    current_level.append(node_name)

            for node_name in current_level:
                placed.add(node_name)
            levels.append(current_level)

        return levels

    # ------------------------------------------------------------------
    # Change 2: Single-node execution helper
    # ------------------------------------------------------------------

    async def _execute_node(
        self,
        node_name: str,
        context: ExecutionContext,
    ) -> Tuple[str, Optional[NodeOutput], Optional[Exception]]:
        """
        Execute a single node (no retry). Returns (name, output, error).

        The output is stored in context immediately on success so that
        subsequent nodes can read it as input.
        """
        node = self.workflow.nodes.get(node_name)
        if not node:
            return (node_name, None, ValueError(f"Node '{node_name}' not found in workflow"))

        executor_class = self._get_executor_class(node.node_type)
        if not executor_class:
            return (node_name, None, ValueError(f"No executor for node type '{node.node_type}'"))

        executor = executor_class(node, self.workflow)
        input_data = context.get_input_for_node(node_name, self.workflow)
        output = await executor.execute(input_data, context)

        context.set_node_output(node_name, output)
        logger.info(f"Node '{node_name}' completed")
        return (node_name, output, None)

    # ------------------------------------------------------------------
    # Change 2: Retry wrapper
    # ------------------------------------------------------------------

    async def _execute_node_with_retry(
        self,
        node_name: str,
        context: ExecutionContext,
    ) -> Tuple[str, Optional[NodeOutput], Optional[Exception]]:
        """
        Execute a node with exponential backoff retry on failure.

        Attempts: up to MAX_RETRIES + 1 total.
        Delays between attempts: RETRY_DELAYS (1 s, 2 s, 4 s).

        On permanent failure the node output is set to {"error": "..."} so
        downstream nodes receive something rather than nothing, and the
        exception is returned to the caller to decide whether to abort.
        """
        last_exc: Optional[Exception] = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                logger.info(
                    f"Executing node '{node_name}' "
                    f"(attempt {attempt + 1}/{self.MAX_RETRIES + 1})"
                )
                return await self._execute_node(node_name, context)

            except Exception as exc:
                last_exc = exc
                if attempt < self.MAX_RETRIES:
                    wait = self.RETRY_DELAYS[attempt]
                    logger.warning(
                        f"Node '{node_name}' attempt {attempt + 1} failed: {exc}. "
                        f"Retrying in {wait}s..."
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        f"Node '{node_name}' failed after "
                        f"{self.MAX_RETRIES + 1} attempts: {exc}"
                    )
                    # Store an error output so downstream nodes have something
                    context.set_node_output(
                        node_name,
                        NodeOutput.single({"error": str(exc)})
                    )

        return (node_name, None, last_exc)

    # ------------------------------------------------------------------
    # Main execution loop
    # ------------------------------------------------------------------

    async def execute(
        self,
        session_id: str = "default",
        chat_history: Optional[List[Dict[str, str]]] = None,
        files: Optional[List[Dict[str, any]]] = None,
    ) -> AsyncGenerator[NodeNotification, None]:
        """
        Execute the workflow and yield NodeNotifications as nodes complete.

        Nodes are grouped into execution levels. Within each level, all
        nodes are independent and run concurrently via asyncio.gather().

        Args:
            session_id:    Session identifier for memory management.
            chat_history:  List of {"role": ..., "content": ...} messages.
            files:         List of uploaded file dicts.

        Yields:
            NodeNotification for each completed node, then a final summary.
        """
        context = self.get_context(session_id)
        context.chat_history = chat_history or []
        context.files = files or []
        context.node_outputs = {}

        execution_order = self.workflow.get_execution_order()

        if not execution_order:
            yield NodeNotification(
                node_name=self.workflow.name,
                session_id=session_id,
                message="No nodes to execute (workflow may be empty or have no start node)",
                notification_type="message",
            )
            return

        execution_levels = self._get_execution_levels(execution_order)
        logger.info(
            f"Executing workflow '{self.workflow.name}' — "
            f"{len(execution_order)} nodes across {len(execution_levels)} level(s)"
        )
        for i, level in enumerate(execution_levels):
            logger.info(f"  Level {i}: {level}")

        last_output: Optional[NodeOutput] = None

        try:
            for level_idx, level_nodes in enumerate(execution_levels):
                logger.info(
                    f"Running level {level_idx + 1}/{len(execution_levels)}: {level_nodes}"
                )

                if len(level_nodes) == 1:
                    # Single node — run directly, no gather overhead
                    _, output, error = await self._execute_node_with_retry(
                        level_nodes[0], context
                    )
                    if error:
                        raise error
                    results = [(level_nodes[0], output, None)]
                else:
                    # Multiple independent nodes — run in parallel
                    tasks = [
                        self._execute_node_with_retry(name, context)
                        for name in level_nodes
                    ]
                    results = await asyncio.gather(*tasks)

                # Yield a notification for each completed node in this level
                for node_name, output, error in results:
                    if error:
                        raise error
                    if output is None:
                        continue

                    last_output = output
                    node = self.workflow.nodes.get(node_name)
                    if node:
                        executor_class = self._get_executor_class(node.node_type)
                        if executor_class:
                            executor = executor_class(node, self.workflow)
                            notification = executor.get_notification(output, context)
                            if notification:
                                yield notification
                                await asyncio.sleep(0.05)  # Give HTTP layer time to flush

            # Final summary notification — include formatted results if present
            last_data = last_output.first_json if last_output else {}
            last_html = last_data.get("html", "")
            result_md = _format_results(last_data)

            final_message = "Workflow executed successfully."
            if result_md:
                final_message = f"Workflow executed successfully.\n\n{result_md}"

            yield NodeNotification(
                node_name=self.workflow.name,
                session_id=session_id,
                message=final_message,
                html=last_html,
                notification_type="message",
            )

        except Exception as e:
            logger.exception(f"Workflow execution failed: {e}")
            yield NodeNotification(
                node_name=self.workflow.name,
                session_id=session_id,
                message=f"Workflow execution failed: {e}",
                notification_type="message",
            )

"""
WorkflowExecutor - the main execution engine for workflows.
"""

import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, List, Optional

from .models import NodeNotification, NodeOutput
from .workflow import Workflow
from .context import ExecutionContext
from .nodes import get_executor_class

logger = logging.getLogger(__name__)


class WorkflowExecutor:
    """
    Main execution engine for n8n workflows.

    This class orchestrates the execution of a workflow by:
    1. Loading and parsing the workflow JSON
    2. Determining execution order (topological sort)
    3. Executing each node in order
    4. Managing data flow between nodes
    5. Managing session contexts internally
    """

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

    async def execute(
        self,
        session_id: str = "default",
        chat_history: Optional[List[Dict[str, str]]] = None,
        files: Optional[List[Dict[str, any]]] = None,
    ) -> AsyncGenerator[NodeNotification, None]:
        """
        Execute the workflow and yield notifications as they occur.

        Args:
            session_id: Session identifier for memory management
            chat_history: List of messages [{"role": "user/assistant", "content": "..."}]
            files: List of uploaded files [{"name": str, "mime": str, "size": int, "content": str}]

        Yields:
            NodeNotification for each node completion and final result
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
                notification_type="message"
            )
            return

        logger.info(f"Executing workflow '{self.workflow.name}' with {len(execution_order)} nodes")
        logger.info(f"Execution order: {execution_order}")

        last_output: Optional[NodeOutput] = None

        try:
            for node_name in execution_order:
                logger.info(f"Executing node: {node_name}")

                node = self.workflow.nodes.get(node_name)
                if not node:
                    raise ValueError(f"Node '{node_name}' not found in workflow")

                executor_class = get_executor_class(node.node_type)
                if not executor_class:
                    raise ValueError(f"No executor found for node type '{node.node_type}'")

                executor = executor_class(node, self.workflow)
                input_data = context.get_input_for_node(node_name, self.workflow)
                output = await executor.execute(input_data, context)

                context.set_node_output(node_name, output)
                last_output = output
                logger.info(f"Node '{node_name}' completed")

                # Yield notification for this node
                notification = executor.get_notification(output, context)
                if notification:
                    yield notification
                    await asyncio.sleep(0.05)  # Give HTTP layer time to send

            # Yield final result
            last_html = ""
            if last_output and last_output.first_item:
                last_html = last_output.first_item.json_data.get("html", "")

            yield NodeNotification(
                node_name=self.workflow.name,
                session_id=session_id,
                message="Workflow executed successfully.",
                html=last_html,
                notification_type="message"
            )

        except Exception as e:
            logger.exception(f"Workflow execution failed: {e}")
            yield NodeNotification(
                node_name=self.workflow.name,
                session_id=session_id,
                message=f"Workflow execution failed: {e}",
                notification_type="message"
            )

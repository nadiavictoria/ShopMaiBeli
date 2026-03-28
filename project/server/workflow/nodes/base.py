"""
BaseNodeExecutor - abstract base class for all node executors.

Data flow format (main connection type only):
- Output: NodeOutput (wraps output_port -> items)
- Input: NodeInput (wraps input_port -> sources -> items)
"""

import logging
from abc import ABC
from typing import Any, Dict, Optional, TYPE_CHECKING

from ..models import Node, NodeData, NodeInput, NodeNotification, NodeOutput

if TYPE_CHECKING:
    from ..context import ExecutionContext
    from ..workflow import Workflow

logger = logging.getLogger(__name__)


class BaseNodeExecutor(ABC):
    """
    Abstract base class for all node executors.

    Data flow:
    - Input: NodeInput - provides convenient access to input items
    - Output: NodeOutput - provides convenient creation of output items

    Main flow nodes (chatTrigger, agent, convertToFile) implement execute().
    AI sub-nodes (memory, tool, lm, parser) are not executed directly;
    they provide capabilities to agent nodes via specific methods.
    """

    # Node type this executor handles (e.g., "chatTrigger", "agent")
    node_type: str = ""

    def __init__(self, node: Node, workflow: "Workflow"):
        self.node = node
        self.workflow = workflow

    async def execute(
        self,
        input_data: NodeInput,
        context: "ExecutionContext"
    ) -> NodeOutput:
        """
        Execute the node logic.

        Args:
            input_data: Input items wrapped in NodeInput
            context: Execution context with runtime state

        Returns:
            Output items wrapped in NodeOutput

        Note: AI sub-nodes (memory, tool, lm, parser) are not executed
        in the main flow. They provide capabilities to agent nodes.
        """
        raise NotImplementedError(
            f"Node type '{self.node_type}' does not support direct execution. "
            "AI sub-nodes should be accessed via agent nodes."
        )

    def get_parameter(self, key: str, default: Any = None) -> Any:
        """Get a parameter value from node configuration."""
        return self.node.parameters.get(key, default)

    def get_nested_parameter(self, path: str, default: Any = None) -> Any:
        """Get a nested parameter value using dot notation (e.g., 'options.systemMessage')."""
        keys = path.split(".")
        value = self.node.parameters
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                logger.debug(f"[{self.node.name}] get_nested_parameter({path}) -> {default} (default, path broken)")
                return default
            if value is None:
                logger.debug(f"[{self.node.name}] get_nested_parameter({path}) -> {default} (default, key not found)")
                return default
        # Truncate long values for readability
        value_preview = str(value)[:200] + "..." if len(str(value)) > 200 else str(value)
        logger.info(f"[{self.node.name}] get_nested_parameter({path}) -> {value_preview}")
        return value

    def create_output(self, data: Dict[str, Any]) -> NodeOutput:
        """Create output with a single item containing the given data."""
        return NodeOutput.single(data)

    def create_item(self, json_data: Dict[str, Any]) -> NodeData:
        """Create a single NodeData item."""
        return NodeData(json_data=json_data)

    def get_notification(
        self,
        output: NodeOutput,
        context: "ExecutionContext"
    ) -> Optional[NodeNotification]:
        """
        Get notification for this node's completion.

        Override this method to return node-specific notifications.
        By default, returns None (no notification).

        Args:
            output: The output produced by this node
            context: Execution context

        Returns:
            NodeNotification or None
        """
        return None

    def get_expression_value(
        self,
        expression: str,
        item: NodeData,
        context: "ExecutionContext"
    ) -> Any:
        """
        Evaluate n8n expression syntax (e.g., "={{ $json.output }}").
        Simplified implementation for common patterns.
        """
        if not isinstance(expression, str):
            return expression

        if not expression.startswith("={{") or not expression.endswith("}}"):
            return expression

        expr = expression[3:-2].strip()

        # Handle $json reference (data from current item)
        if expr.startswith("$json."):
            path = expr[6:]  # Remove "$json."
            data = item.json_data
            for key in path.split("."):
                if isinstance(data, dict):
                    data = data.get(key)
                else:
                    logger.info(f"[{self.node.name}] get_expression_value({expression}) -> None (path broken at '{key}')")
                    return None
            # Truncate long values for readability
            data_preview = str(data)[:200] + "..." if len(str(data)) > 200 else str(data)
            logger.info(f"[{self.node.name}] get_expression_value({expression}) -> {data_preview}")
            return data

        logger.debug(f"[{self.node.name}] get_expression_value({expression}) -> {expression} (unrecognized pattern)")
        return expression

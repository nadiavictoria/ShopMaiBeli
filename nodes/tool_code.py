"""
ToolCodeExecutor - handles toolCode node (Python code as AI tool).

This is an AI sub-node that provides tool capabilities to agent nodes.
It is not executed directly in the main flow.
"""

import json
import traceback
from typing import Dict, Any
from .base import BaseNodeExecutor
from workflow_engine.context import ExecutionContext


class ToolCodeExecutor(BaseNodeExecutor):
    """
    Handles toolCode node - executes Python code as an AI tool.

    This node is not executed in the main flow. Instead, agent nodes
    access it to get tool definitions and execute tool calls.
    """

    node_type = "toolCode"

    def get_tool_definition(self) -> Dict[str, Any]:
        """
        Get the tool definition for this code tool.

        Returns:
            Dict with name, description, code, and language
        """
        return {
            "name": self.node.name,
            "description": self.get_parameter("description", ""),
            "language": self.get_parameter("language", "python"),
        }

    async def execute_tool(self, query: str, context: ExecutionContext) -> str:
        """
        Execute the tool code with the given query.
        Called by the agent when it invokes this tool.

        Following n8n convention, the code uses _query global variable for input
        and uses return statement for output.
        """
        python_code = self.get_parameter("pythonCode", "")

        # Create execution namespace with _query variable (n8n convention)
        # Tools can import any module they need via import statements
        namespace = {
            "_query": query,
            "__builtins__": __builtins__,
        }

        # Wrap code in a function to handle return statements
        # n8n Code Tool expects the last statement to be a return
        wrapped_code = "def __tool_func__():\n"
        for line in python_code.split("\n"):
            wrapped_code += f"    {line}\n"
        wrapped_code += "__result__ = __tool_func__()"

        try:
            exec(wrapped_code, namespace)
            result = namespace.get("__result__", "")
            return str(result) if result is not None else ""
        except Exception as e:
            error_msg = f"Tool execution error: {str(e)}\n{traceback.format_exc()}"
            return json.dumps({"error": error_msg}, ensure_ascii=False)

"""
MemoryBufferExecutor - handles memoryBufferWindow node.

This is an AI sub-node that provides conversation memory to agent nodes.
It is not executed directly in the main flow.
"""

from typing import List, Dict, Any
from .base import BaseNodeExecutor
from ..context import ExecutionContext


class MemoryBufferExecutor(BaseNodeExecutor):
    """
    Handles memoryBufferWindow node - provides conversation memory to agents.

    This node is not executed in the main flow. Instead, agent nodes
    access it directly to get conversation history.
    """

    node_type = "memoryBufferWindow"

    def get_memory(self, context: ExecutionContext) -> List[Dict[str, Any]]:
        """
        Get conversation memory for the current session.

        Args:
            context: Execution context with memory storage

        Returns:
            List of message dicts with 'role' and 'content'
        """
        window_size = self.get_parameter("windowSize", 5)

        # Get memory using this node's name as key
        memory_key = self.node.name
        memory = context.memory.get(memory_key, [])

        # Apply window size limit
        if len(memory) > window_size:
            memory = memory[-window_size:]

        return memory

    def add_to_memory(self, context: ExecutionContext, role: str, content: str):
        """
        Add a message to memory.

        Args:
            context: Execution context with memory storage
            role: Message role ("user", "assistant", or "tool")
            content: Message content
        """
        memory_key = self.node.name
        if memory_key not in context.memory:
            context.memory[memory_key] = []
        context.memory[memory_key].append({"role": role, "content": content})

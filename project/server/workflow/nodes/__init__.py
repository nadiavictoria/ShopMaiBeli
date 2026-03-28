"""
Node executors package - contains executors for each node type.
"""

from .base import BaseNodeExecutor
from .chat_trigger import ChatTriggerExecutor
from .memory_buffer import MemoryBufferExecutor
from .tool_code import ToolCodeExecutor
from .output_parser import OutputParserExecutor
from .convert_to_file import ConvertToFileExecutor
from .agent import AgentExecutor
from .lm_deepseek import DeepSeekExecutor

# Registry mapping node types to their executors
NODE_EXECUTOR_REGISTRY = {
    "chatTrigger": ChatTriggerExecutor,
    "memoryBufferWindow": MemoryBufferExecutor,
    "toolCode": ToolCodeExecutor,
    "outputParserStructured": OutputParserExecutor,
    "convertToFile": ConvertToFileExecutor,
    "agent": AgentExecutor,
    "lmChatDeepSeek": DeepSeekExecutor,
}


def get_executor_class(node_type: str):
    """Get the executor class for a given node type."""
    return NODE_EXECUTOR_REGISTRY.get(node_type)


__all__ = [
    "BaseNodeExecutor",
    "ChatTriggerExecutor",
    "MemoryBufferExecutor",
    "ToolCodeExecutor",
    "OutputParserExecutor",
    "ConvertToFileExecutor",
    "AgentExecutor",
    "DeepSeekExecutor",
    "NODE_EXECUTOR_REGISTRY",
    "get_executor_class",
]

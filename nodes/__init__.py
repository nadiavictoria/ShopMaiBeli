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
from .product_search import ProductSearchExecutor
from .review_analyzer import ReviewAnalyzerExecutor
from .trust_scorer import TrustScorerExecutor

# Lazy import for DeepSeekExecutor (requires openai package)
_DeepSeekExecutor = None

def _get_deepseek_executor():
    """Lazy import of DeepSeekExecutor to avoid import errors if openai is not installed."""
    global _DeepSeekExecutor
    if _DeepSeekExecutor is None:
        try:
            from .lm_deepseek import DeepSeekExecutor
            _DeepSeekExecutor = DeepSeekExecutor
        except ImportError:
            # openai package not installed; return None or a placeholder
            _DeepSeekExecutor = None
    return _DeepSeekExecutor


# Registry mapping node types to their executors
NODE_EXECUTOR_REGISTRY = {
    "chatTrigger": ChatTriggerExecutor,
    "memoryBufferWindow": MemoryBufferExecutor,
    "toolCode": ToolCodeExecutor,
    "outputParserStructured": OutputParserExecutor,
    "convertToFile": ConvertToFileExecutor,
    "agent": AgentExecutor,
    "productSearch": ProductSearchExecutor,
    "reviewAnalyzer": ReviewAnalyzerExecutor,
    "trustScorer": TrustScorerExecutor,
}

# Register DeepSeekExecutor only if it can be imported
_deepseek_cls = _get_deepseek_executor()
if _deepseek_cls is not None:
    NODE_EXECUTOR_REGISTRY["lmChatDeepSeek"] = _deepseek_cls


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
    "ProductSearchExecutor",
    "ReviewAnalyzerExecutor",
    "TrustScorerExecutor",
    "NODE_EXECUTOR_REGISTRY",
    "get_executor_class",
]

# Conditionally export DeepSeekExecutor if available
if _deepseek_cls is not None:
    __all__.append("DeepSeekExecutor")

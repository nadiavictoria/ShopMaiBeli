from .chat_trigger import ChatTriggerExecutor
from .agent import AgentExecutor
from .product_search import ProductSearchExecutor
from .review_analyzer import ReviewAnalyzerExecutor
from .convert_to_file import ConvertToFileExecutor
from .lm_deepseek import DeepSeekExecutor
from .memory_buffer import MemoryBufferExecutor
from .output_parser import OutputParserExecutor
from .tool_code import ToolCodeExecutor

NODE_EXECUTOR_REGISTRY = {
    "chatTrigger": ChatTriggerExecutor,
    "agent": AgentExecutor,
    "productSearch": ProductSearchExecutor,
    "reviewAnalyzer": ReviewAnalyzerExecutor,
    "convertToFile": ConvertToFileExecutor,
    "lmChatDeepSeek": DeepSeekExecutor,
    "memoryBufferWindow": MemoryBufferExecutor,
    "outputParserStructured": OutputParserExecutor,
    "toolCode": ToolCodeExecutor,
}


def get_executor_class(node_type: str):
    executor_class = NODE_EXECUTOR_REGISTRY.get(node_type)
    if executor_class is None:
        raise ValueError(f"No executor registered for node type: '{node_type}'")
    return executor_class

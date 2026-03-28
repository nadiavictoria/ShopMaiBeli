"""
DeepSeekExecutor - handles lmChatDeepSeek node (DeepSeek language model).

This is an AI sub-node that provides LLM capabilities to agent nodes.
It is not executed directly in the main flow.
"""

import os
from openai import OpenAI
from typing import Any, Dict, List, Optional
from .base import BaseNodeExecutor


class DeepSeekExecutor(BaseNodeExecutor):
    """
    Handles lmChatDeepSeek node - calls DeepSeek API using OpenAI SDK.

    This node is not executed in the main flow. Instead, agent nodes
    access it to make LLM API calls.
    """

    node_type = "lmChatDeepSeek"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._client: Optional[OpenAI] = None

    def _get_client(self) -> "OpenAI":
        """Get or create OpenAI client for DeepSeek API."""
        if self._client is not None:
            return self._client

        # Get API key from environment
        api_key = os.environ.get("DEEPSEEK_API_KEY")

        if not api_key:
            raise ValueError("DeepSeek API key not found. Set DEEPSEEK_API_KEY environment variable.")

        self._client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
        return self._client

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Make a chat completion request to DeepSeek API.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions for function calling

        Returns:
            Dict with 'content' and optionally 'tool_calls'
        """
        client = self._get_client()

        # Get parameters from node config with defaults
        options = self.get_parameter("options", {})
        model = options.get("model", "deepseek-chat")
        temperature = options.get("temperature", 0.7)
        max_tokens = options.get("maxTokens", 4096)

        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            # Convert tools to OpenAI function calling format
            openai_tools = []
            for tool in tools:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.get("name", "").replace(" ", "_"),
                        "description": tool.get("description", ""),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "_query": {
                                    "type": "string",
                                    "description": "The query/input for the tool"
                                }
                            },
                            "required": ["_query"]
                        }
                    }
                })
            kwargs["tools"] = openai_tools

        response = client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        result = {
            "content": choice.message.content or "",
            "finish_reason": choice.finish_reason,
        }

        if choice.message.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                }
                for tc in choice.message.tool_calls
            ]

        return result

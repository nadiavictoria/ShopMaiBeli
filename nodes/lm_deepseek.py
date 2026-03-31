import os
import httpx
from workflow_engine.models import NodeInput, NodeOutput
from .base import BaseNodeExecutor


class DeepSeekExecutor(BaseNodeExecutor):
    node_type = "lmChatDeepSeek"

    async def execute(self, input_data: NodeInput, context) -> NodeOutput:
        return self.create_output({})

    async def chat_completion(self, messages: list[dict], system_prompt: str = "") -> str:
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if not api_key:
            return "[DeepSeek API key not configured — set DEEPSEEK_API_KEY in backend/.env]"

        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "deepseek-chat",
                    "messages": full_messages,
                    "max_tokens": 4096
                }
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

from workflow_engine.models import NodeInput, NodeOutput
from .base import BaseNodeExecutor


class MemoryBufferExecutor(BaseNodeExecutor):
    node_type = "memoryBufferWindow"

    async def execute(self, input_data: NodeInput, context) -> NodeOutput:
        return self.create_output({})

    def get_messages(self, context) -> list[dict]:
        return context.memory.get(context.session_id, [])

    def add_message(self, context, role: str, content: str):
        session_id = context.session_id
        if session_id not in context.memory:
            context.memory[session_id] = []
        max_messages = self.get_parameter("windowSize", 10) * 2
        context.memory[session_id].append({"role": role, "content": content})
        if len(context.memory[session_id]) > max_messages:
            context.memory[session_id] = context.memory[session_id][-max_messages:]

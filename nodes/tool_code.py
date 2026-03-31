from workflow_engine.models import NodeInput, NodeOutput
from .base import BaseNodeExecutor


class ToolCodeExecutor(BaseNodeExecutor):
    node_type = "toolCode"

    async def execute(self, input_data: NodeInput, context) -> NodeOutput:
        return self.create_output({})

    async def run(self, input_data: dict, context) -> dict:
        return {"result": f"Tool '{self.node.name}' executed"}

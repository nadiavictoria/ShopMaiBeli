import json
from workflow_engine.models import NodeInput, NodeOutput
from .base import BaseNodeExecutor


class OutputParserExecutor(BaseNodeExecutor):
    node_type = "outputParserStructured"

    async def execute(self, input_data: NodeInput, context) -> NodeOutput:
        return self.create_output({})

    def get_format_instructions(self) -> str:
        schema = self.get_parameter("jsonSchemaExample", "{}")
        return f"Respond with valid JSON matching this schema: {schema}"

    def parse(self, text: str) -> dict:
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
        return {"output": text}

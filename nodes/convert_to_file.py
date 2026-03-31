from workflow_engine.models import NodeInput, NodeOutput, NodeNotification
from .base import BaseNodeExecutor


class ConvertToFileExecutor(BaseNodeExecutor):
    node_type = "convertToFile"

    async def execute(self, input_data: NodeInput, context) -> NodeOutput:
        input_json = input_data.first_json
        source_property = self.get_parameter("sourceProperty", "output")

        content = input_json
        for key in source_property.split("."):
            if isinstance(content, dict):
                content = content.get(key, "")
            else:
                break

        if not isinstance(content, str):
            content = str(content)

        filename = self.get_parameter("options", {}).get("fileName", "report.html")
        return self.create_output({
            "html": content,
            "filename": filename,
            "fileContent": content
        })

    def get_notification(self, output: NodeOutput, context) -> NodeNotification:
        return NodeNotification(
            node_name=self.node.name,
            session_id=context.session_id,
            message="Report ready",
            notification_type="message",
            data=output.first_json
        )

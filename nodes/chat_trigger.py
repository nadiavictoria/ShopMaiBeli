from workflow_engine.models import NodeInput, NodeOutput, NodeNotification
from .base import BaseNodeExecutor


class ChatTriggerExecutor(BaseNodeExecutor):
    node_type = "chatTrigger"

    async def execute(self, input_data: NodeInput, context) -> NodeOutput:
        last_user_msg = ""
        for msg in reversed(context.chat_history):
            if msg.get("role") == "user":
                last_user_msg = msg.get("content", "")
                break
        return self.create_output({
            "chatInput": last_user_msg,
            "sessionId": context.session_id
        })

    def get_notification(self, output: NodeOutput, context) -> NodeNotification:
        return NodeNotification(
            node_name=self.node.name,
            session_id=context.session_id,
            message=f"Received query: {output.first_json.get('chatInput', '')}",
            notification_type="step",
            data=output.first_json
        )

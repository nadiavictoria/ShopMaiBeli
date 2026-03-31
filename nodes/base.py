from abc import ABC, abstractmethod
from workflow_engine.models import NodeInput, NodeOutput, NodeNotification, Node


class BaseNodeExecutor(ABC):
    def __init__(self, node: Node, workflow):
        self.node = node
        self.workflow = workflow

    def get_parameter(self, key: str, default=None):
        return self.node.parameters.get(key, default)

    def create_output(self, data: dict) -> NodeOutput:
        from workflow_engine.models import NodeData
        return NodeOutput(ports=[[NodeData(json_data=data)]])

    @abstractmethod
    async def execute(self, input_data: NodeInput, context) -> NodeOutput:
        pass

    def get_notification(self, output: NodeOutput, context) -> NodeNotification:
        return NodeNotification(
            node_name=self.node.name,
            session_id=context.session_id,
            message=f"Node '{self.node.name}' completed",
            notification_type="step",
            data=output.first_json
        )

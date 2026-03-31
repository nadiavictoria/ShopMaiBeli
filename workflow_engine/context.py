from dataclasses import dataclass, field
from .models import NodeOutput, NodeInput, NodeData


@dataclass
class ExecutionContext:
    session_id: str
    chat_history: list = field(default_factory=list)
    files: list = field(default_factory=list)
    node_outputs: dict = field(default_factory=dict)
    memory: dict = field(default_factory=dict)

    def set_node_output(self, node_name: str, output: NodeOutput):
        self.node_outputs[node_name] = output

    def get_node_output(self, node_name: str) -> NodeOutput | None:
        return self.node_outputs.get(node_name)

    def get_input_for_node(self, node_name: str, workflow) -> NodeInput:
        parents = workflow.get_parent_nodes(node_name)

        if not parents:
            # Root node — build input from chat history
            last_user_msg = ""
            for msg in reversed(self.chat_history):
                if msg.get("role") == "user":
                    last_user_msg = msg.get("content", "")
                    break
            return NodeInput(ports=[[
                [NodeData(json_data={"chatInput": last_user_msg, "sessionId": self.session_id})]
            ]])

        # Merge outputs from all parents into a single port
        all_items = []
        for parent_name in parents:
            parent_output = self.node_outputs.get(parent_name)
            if parent_output and parent_output.ports:
                all_items.extend(parent_output.ports[0])

        return NodeInput(ports=[[all_items]] if all_items else [[[]]])

import uuid
from .models import Node


class Workflow:
    def __init__(self, workflow_json: dict):
        self.name = workflow_json.get("name", "ShopMaiBeli Workflow")
        self.raw = workflow_json
        self.nodes: dict[str, Node] = {}
        self.connections: dict = workflow_json.get("connections", {})

        for node_data in workflow_json.get("nodes", []):
            node = Node(
                id=node_data.get("id", str(uuid.uuid4())),
                name=node_data["name"],
                type=node_data.get("type", ""),
                type_version=float(node_data.get("typeVersion", 1.0)),
                position=tuple(node_data.get("position", [0, 0])),
                parameters=node_data.get("parameters", {})
            )
            self.nodes[node.name] = node

    def get_children(self, node_name: str) -> list[str]:
        """Main-flow children of this node."""
        node_connections = self.connections.get(node_name, {})
        children = []

        if isinstance(node_connections, list):
            # Simplified format: {NodeA: [NodeB]}
            children = node_connections
        elif isinstance(node_connections, dict):
            # n8n format: {NodeA: {main: [[{node: NodeB, ...}]]}}
            for conn_type, outputs in node_connections.items():
                if conn_type == "main":
                    for output_list in outputs:
                        for conn in output_list:
                            if isinstance(conn, dict) and "node" in conn:
                                children.append(conn["node"])

        return [c for c in children if c in self.nodes]

    def get_parent_nodes(self, node_name: str) -> list[str]:
        """Nodes whose main-flow output feeds into node_name."""
        return [name for name in self.nodes if node_name in self.get_children(name)]

    def get_execution_order(self) -> list[str]:
        """Topological sort of main-flow nodes (Kahn's algorithm)."""
        in_degree = {name: 0 for name in self.nodes}
        for name in self.nodes:
            for child in self.get_children(name):
                in_degree[child] += 1

        queue = [name for name, deg in in_degree.items() if deg == 0]
        order = []
        while queue:
            node = queue.pop(0)
            order.append(node)
            for child in self.get_children(node):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        return order

    def get_sub_nodes(self, node_name: str) -> dict[str, Node]:
        """AI sub-nodes (LLM, memory, tools, output parser) attached to a node."""
        sub_nodes = {}
        node_connections = self.connections.get(node_name, {})
        if not isinstance(node_connections, dict):
            return sub_nodes

        ai_types = ("ai_languageModel", "ai_memory", "ai_tool", "ai_outputParser")
        for conn_type in ai_types:
            if conn_type in node_connections:
                for output_list in node_connections[conn_type]:
                    for conn in output_list:
                        if isinstance(conn, dict) and "node" in conn:
                            sub_name = conn["node"]
                            if sub_name in self.nodes:
                                sub_nodes[sub_name] = self.nodes[sub_name]
        return sub_nodes

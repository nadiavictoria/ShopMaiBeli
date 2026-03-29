"""
Workflow class - parses n8n workflow JSON and builds connection graphs.
"""

from typing import Dict, List, Optional
from .models import Node, NodeConnection, SourceConnection, ConnectionType


class Workflow:
    """
    Parses n8n workflow JSON and builds connection graphs.
    Mirrors n8n's Workflow class functionality.
    """

    def __init__(self, workflow_json: dict):
        self.id = workflow_json.get("id", "")
        self.name = workflow_json.get("name", "Unnamed Workflow")
        self.settings = workflow_json.get("settings", {})

        # Parse nodes
        self.nodes: Dict[str, Node] = {}
        self._parse_nodes(workflow_json.get("nodes", []))

        # Build connection maps (bidirectional)
        # Source node -> {connection_type -> [[NodeConnection, ...], ...]}
        # Indexed by source output index
        self.connections_by_source: Dict[str, Dict[ConnectionType, List[List[NodeConnection]]]] = {}
        # Destination node -> {connection_type -> [[SourceConnection, ...], ...]}
        # Indexed by destination input index
        self.connections_by_destination: Dict[str, Dict[ConnectionType, List[List[SourceConnection]]]] = {}
        self._parse_connections(workflow_json.get("connections", {}))

    def _parse_nodes(self, nodes_list: list):
        """Parse nodes array into Node objects."""
        for node_data in nodes_list:
            node = Node(
                id=node_data.get("id", ""),
                name=node_data.get("name", ""),
                type=node_data.get("type", ""),
                type_version=node_data.get("typeVersion", 1.0),
                position=tuple(node_data.get("position", [0, 0])),
                parameters=node_data.get("parameters", {}),
                credentials=node_data.get("credentials", {}),
                webhook_id=node_data.get("webhookId"),
            )
            self.nodes[node.name] = node

    def _parse_connections(self, connections_dict: dict):
        """
        Parse connections and build bidirectional maps.

        Input format:
        {
            "Source Node Name": {
                "main": [[{"node": "Target", "type": "main", "index": 0}]]
            }
        }
        """
        for source_name, type_connections in connections_dict.items():
            if source_name not in self.connections_by_source:
                self.connections_by_source[source_name] = {}

            for conn_type_str, outputs in type_connections.items():
                conn_type = ConnectionType(conn_type_str)

                if conn_type not in self.connections_by_source[source_name]:
                    self.connections_by_source[source_name][conn_type] = []

                for output_index, connections in enumerate(outputs):
                    # Ensure list is long enough
                    while len(self.connections_by_source[source_name][conn_type]) <= output_index:
                        self.connections_by_source[source_name][conn_type].append([])

                    for conn_data in connections:
                        target_name = conn_data["node"]
                        target_type = ConnectionType(conn_data["type"])
                        target_index = conn_data["index"]

                        # Add to source map
                        node_conn = NodeConnection(
                            node=target_name,
                            type=target_type,
                            index=target_index
                        )
                        self.connections_by_source[source_name][conn_type][output_index].append(node_conn)

                        # Add to destination map (store source info with output_index)
                        if target_name not in self.connections_by_destination:
                            self.connections_by_destination[target_name] = {}
                        if target_type not in self.connections_by_destination[target_name]:
                            self.connections_by_destination[target_name][target_type] = []

                        # Ensure list is long enough for target index
                        while len(self.connections_by_destination[target_name][target_type]) <= target_index:
                            self.connections_by_destination[target_name][target_type].append([])

                        source_conn = SourceConnection(
                            node=source_name,
                            output_index=output_index
                        )
                        self.connections_by_destination[target_name][target_type][target_index].append(source_conn)

    def get_start_node(self) -> Optional[Node]:
        """Find the trigger node (entry point) of the workflow."""
        for node in self.nodes.values():
            if node.is_trigger:
                return node

        # Fallback: find node with no incoming 'main' connections
        for node in self.nodes.values():
            dest_conns = self.connections_by_destination.get(node.name, {})
            if ConnectionType.MAIN not in dest_conns or not dest_conns[ConnectionType.MAIN]:
                # Also check it has outgoing main connections (not a leaf node)
                source_conns = self.connections_by_source.get(node.name, {})
                if ConnectionType.MAIN in source_conns:
                    return node

        return None

    def get_parent_nodes(self, node_name: str, conn_type: ConnectionType = ConnectionType.MAIN) -> List[str]:
        """Get all parent node names connected via the specified connection type."""
        dest_conns = self.connections_by_destination.get(node_name, {})
        type_conns = dest_conns.get(conn_type, [])

        parents = []
        for index_list in type_conns:
            for source_conn in index_list:
                parents.append(source_conn.node)
        return parents

    def get_child_nodes(self, node_name: str, conn_type: ConnectionType = ConnectionType.MAIN) -> List[str]:
        """Get all child node names connected via the specified connection type."""
        source_conns = self.connections_by_source.get(node_name, {})
        type_conns = source_conns.get(conn_type, [])

        children = []
        for output_list in type_conns:
            for conn in output_list:
                children.append(conn.node)
        return children

    def get_ai_sub_nodes(self, agent_node_name: str) -> Dict[ConnectionType, List[str]]:
        """
        Get all AI sub-nodes (tools, memory, model, parser) connected to an agent.
        These are nodes that provide capabilities to the agent.
        """
        result = {}
        dest_conns = self.connections_by_destination.get(agent_node_name, {})

        for conn_type in [ConnectionType.AI_TOOL, ConnectionType.AI_MEMORY,
                          ConnectionType.AI_LANGUAGE_MODEL, ConnectionType.AI_OUTPUT_PARSER]:
            if conn_type in dest_conns:
                sources = []
                for index_list in dest_conns[conn_type]:
                    for source_conn in index_list:
                        sources.append(source_conn.node)
                if sources:
                    result[conn_type] = sources

        return result

    def get_execution_order(self) -> List[str]:
        """
        Get topological execution order for main flow nodes using Kahn's algorithm.
        """
        start = self.get_start_node()
        if not start:
            return []

        # Find all nodes reachable in main flow
        main_flow_nodes = set()
        queue = [start.name]
        while queue:
            node_name = queue.pop(0)
            if node_name in main_flow_nodes:
                continue
            main_flow_nodes.add(node_name)
            children = self.get_child_nodes(node_name, ConnectionType.MAIN)
            queue.extend(children)

        # Calculate in-degree for each node
        in_degree = {name: 0 for name in main_flow_nodes}
        for node_name in main_flow_nodes:
            parents = self.get_parent_nodes(node_name, ConnectionType.MAIN)
            in_degree[node_name] = len([p for p in parents if p in main_flow_nodes])

        # Kahn's algorithm
        ready = [name for name, deg in in_degree.items() if deg == 0]
        order = []

        while ready:
            node_name = ready.pop(0)
            order.append(node_name)

            for child in self.get_child_nodes(node_name, ConnectionType.MAIN):
                if child in in_degree:
                    in_degree[child] -= 1
                    if in_degree[child] == 0:
                        ready.append(child)

        if len(order) != len(main_flow_nodes):
            raise ValueError("Workflow contains a cycle")

        return order

    def __repr__(self) -> str:
        return f"Workflow(name='{self.name}', nodes={len(self.nodes)})"

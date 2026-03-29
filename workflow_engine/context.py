"""
ExecutionContext - manages runtime state for workflow execution.
"""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Dict, List, TYPE_CHECKING

from .models import NodeInput, NodeOutput, ConnectionType

if TYPE_CHECKING:
    from .workflow import Workflow


@dataclass
class ExecutionContext:
    """
    Runtime context for workflow execution.
    Manages state, data flow, and provides utilities for node executors.

    Primary inputs:
    - session_id: Session identifier
    - chat_history: List of messages [{"role": "user/assistant", "content": "..."}]
    - files: List of uploaded files [{"name": str, "mime": str, "size": int, "content": str (base64)}]

    Node output storage:
    - node_outputs: Dict[node_name, NodeOutput]
    """

    # Primary inputs for workflow execution
    session_id: str = "default"
    chat_history: List[Dict[str, str]] = field(default_factory=list)
    files: List[Dict[str, any]] = field(default_factory=list)  # Uploaded files

    # Node execution results: node_name -> NodeOutput
    node_outputs: Dict[str, NodeOutput] = field(default_factory=dict)

    # Memory storage for agent nodes (keyed by memory_node_name)
    # Each memory node has its own conversation history
    memory: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)

    # Execution metadata
    execution_id: str = ""
    workflow_id: str = ""

    def get_input_for_node(
        self,
        node_name: str,
        workflow: "Workflow"
    ) -> NodeInput:
        """
        Gather main flow input data for a node from its parent nodes.

        Only handles 'main' connection type. AI sub-nodes (tools, memory, model, parser)
        provide configuration directly to agent nodes, not through this method.

        Returns:
            NodeInput wrapping input_port -> sources -> items
        """
        dest_conns = workflow.connections_by_destination.get(node_name, {})

        # Only process main connections
        if ConnectionType.MAIN not in dest_conns:
            return NodeInput(ports=[])

        index_lists = dest_conns[ConnectionType.MAIN]
        ports = []

        for source_connections in index_lists:
            sources_data = []
            for source_conn in source_connections:
                source_name = source_conn.node
                source_output_index = source_conn.output_index

                if source_name in self.node_outputs:
                    source_output = self.node_outputs[source_name]

                    # Get data from the specific output port (deep copy to avoid mutation)
                    items = source_output.get_items(source_output_index)
                    if items:
                        sources_data.append(deepcopy(items))

            ports.append(sources_data)

        return NodeInput(ports=ports)

    def set_node_output(self, node_name: str, output: NodeOutput):
        """Store the output of a node execution."""
        self.node_outputs[node_name] = output

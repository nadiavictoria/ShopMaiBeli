"""
Data models for the workflow execution engine.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum


class ConnectionType(str, Enum):
    """Connection types matching n8n's NodeConnectionType."""
    MAIN = "main"
    AI_TOOL = "ai_tool"
    AI_MEMORY = "ai_memory"
    AI_LANGUAGE_MODEL = "ai_languageModel"
    AI_OUTPUT_PARSER = "ai_outputParser"


@dataclass
class NodeConnection:
    """Represents a single connection to another node (from source perspective)."""
    node: str                    # Target node name
    type: ConnectionType         # Connection type
    index: int                   # Input index on target node


@dataclass
class SourceConnection:
    """Represents a connection from a source node (from destination perspective)."""
    node: str                    # Source node name
    output_index: int            # Output index on source node


@dataclass
class Node:
    """Represents a workflow node."""
    id: str
    name: str
    type: str                    # e.g., "@n8n/n8n-nodes-langchain.agent"
    type_version: float
    position: Tuple[int, int]
    parameters: Dict[str, Any] = field(default_factory=dict)
    credentials: Dict[str, Any] = field(default_factory=dict)
    webhook_id: Optional[str] = None

    @property
    def node_type(self) -> str:
        """Extract the node type name (e.g., 'agent' from '@n8n/n8n-nodes-langchain.agent')."""
        return self.type.split(".")[-1]

    @property
    def is_trigger(self) -> bool:
        """Check if this is a trigger node."""
        return "trigger" in self.node_type.lower()


@dataclass
class NodeData:
    """Data passed between nodes."""
    json_data: Dict[str, Any] = field(default_factory=dict)
    binary_data: Optional[bytes] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NodeOutput:
    """
    Output from a node execution.

    Structure: output_port -> items
    Most nodes have a single output port with a single item.
    """
    ports: List[List[NodeData]] = field(default_factory=list)

    @classmethod
    def single(cls, data: Dict[str, Any]) -> "NodeOutput":
        """Create output with a single item on port 0."""
        return cls(ports=[[NodeData(json_data=data)]])

    @classmethod
    def from_item(cls, item: NodeData) -> "NodeOutput":
        """Create output with a single NodeData item on port 0."""
        return cls(ports=[[item]])

    @classmethod
    def from_items(cls, items: List[NodeData], port: int = 0) -> "NodeOutput":
        """Create output with multiple items on a specific port."""
        ports = []
        for _ in range(port + 1):
            ports.append([])
        ports[port] = items
        return cls(ports=ports)

    @property
    def first_item(self) -> Optional[NodeData]:
        """Get the first item from port 0, or None if empty."""
        if self.ports and self.ports[0]:
            return self.ports[0][0]
        return None

    @property
    def first_json(self) -> Dict[str, Any]:
        """Get json_data from the first item, or empty dict if none."""
        item = self.first_item
        return item.json_data if item else {}

    def get_items(self, port: int = 0) -> List[NodeData]:
        """Get all items from a specific port."""
        if port < len(self.ports):
            return self.ports[port]
        return []


@dataclass
class NodeInput:
    """
    Input to a node execution.

    Structure: input_port -> sources -> items
    Most nodes have a single input port with items from one source.
    """
    ports: List[List[List[NodeData]]] = field(default_factory=list)

    @property
    def first_item(self) -> Optional[NodeData]:
        """Get the first item from port 0, source 0, or None if empty."""
        if self.ports and self.ports[0] and self.ports[0][0]:
            return self.ports[0][0][0]
        return None

    @property
    def first_json(self) -> Dict[str, Any]:
        """Get json_data from the first item, or empty dict if none."""
        item = self.first_item
        return item.json_data if item else {}

    def get_items(self, port: int = 0) -> List[NodeData]:
        """
        Get all items from a specific port, merged from all sources.
        """
        if port >= len(self.ports):
            return []
        items = []
        for source_items in self.ports[port]:
            items.extend(source_items)
        return items

    def is_empty(self) -> bool:
        """Check if there are no input items."""
        return not self.ports or all(
            not sources or all(not items for items in sources)
            for sources in self.ports
        )


@dataclass
class NodeNotification:
    """
    Notification sent from a node to the frontend during execution.

    Used to display real-time progress, status updates, or intermediate results.
    """
    node_name: str               # Name of the node sending the notification
    session_id: str              # Session identifier
    message: str = ""            # Text message to display
    html: str = ""               # Optional HTML content
    data: Dict[str, Any] = field(default_factory=dict)  # Additional data
    notification_type: str = "step"  # "step" or "message"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for HTTP request."""
        return {
            "type": self.notification_type,
            "name": self.node_name,
            "text": self.message,
            "html": self.html,
            "session_id": self.session_id,
            "data": self.data,
        }

    def to_json(self) -> str:
        """Convert to NDJSON line for streaming."""
        return json.dumps(self.to_dict(), ensure_ascii=False) + "\n"

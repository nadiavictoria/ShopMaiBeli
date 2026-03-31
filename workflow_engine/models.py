from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class NodeData:
    json_data: dict = field(default_factory=dict)
    binary_data: Optional[bytes] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class NodeInput:
    """Represents input data flowing into a node.
    
    Structure: ports[port_index][source_index][item_index]
    """
    ports: list = field(default_factory=list)

    @property
    def first_json(self) -> dict:
        """Get JSON data from the first item of the first port."""
        if self.ports and self.ports[0] and self.ports[0][0]:
            first = self.ports[0][0]
            if isinstance(first, list) and first:
                return first[0].json_data if isinstance(first[0], NodeData) else {}
            elif isinstance(first, NodeData):
                return first.json_data
        return {}

    def get_items(self, port: int = 0) -> list:
        """Get all NodeData items from a specific port, flattening sources."""
        if port >= len(self.ports):
            return []
        items = []
        for source in self.ports[port]:
            if isinstance(source, list):
                items.extend(source)
            elif isinstance(source, NodeData):
                items.append(source)
        return items


@dataclass
class NodeOutput:
    """Represents output data from a node.
    
    Structure: ports[port_index][item_index]
    """
    ports: list = field(default_factory=list)

    @classmethod
    def single(cls, data: dict) -> "NodeOutput":
        """Create a simple single-item output."""
        return cls(ports=[[NodeData(json_data=data)]])

    @property
    def first_json(self) -> dict:
        if self.ports and self.ports[0]:
            first = self.ports[0][0]
            return first.json_data if isinstance(first, NodeData) else {}
        return {}


@dataclass
class Node:
    id: str
    name: str
    type: str
    type_version: float
    position: tuple
    parameters: dict = field(default_factory=dict)

    @property
    def node_type(self) -> str:
        """Short node type — last segment after dot."""
        return self.type.split(".")[-1]


@dataclass
class NodeNotification:
    node_name: str
    session_id: str
    message: str
    notification_type: str = "step"   # "step" or "message"
    data: dict = field(default_factory=dict)

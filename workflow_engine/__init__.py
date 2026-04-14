"""
n8n Workflow Execution Engine - Python Implementation

This package provides a simplified Python implementation of n8n's workflow
parsing and execution logic.
"""

from .models import (
    ConnectionType,
    NodeConnection,
    Node,
    NodeData,
    NodeInput,
    NodeOutput,
    NodeNotification,
)
from .workflow import Workflow
from .context import ExecutionContext
from .executor import WorkflowExecutor
from .session_store import session_store, SessionStore

__all__ = [
    "ConnectionType",
    "NodeConnection",
    "Node",
    "NodeData",
    "NodeInput",
    "NodeOutput",
    "NodeNotification",
    "Workflow",
    "ExecutionContext",
    "WorkflowExecutor",
    "SessionStore",
    "session_store",
]

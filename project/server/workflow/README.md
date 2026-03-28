# n8n Workflow Execution Engine (Python)

A simplified Python implementation of n8n's workflow parsing and execution logic. This engine allows you to define workflows in n8n JSON format and execute them with Python.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Workflow Execution Engine                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                     WorkflowExecutor (executor.py)                  │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────┐ │ │
│  │  │ from_file() │  │ execute()   │  │ Session Context Management  │ │ │
│  │  │ from_json() │  │ (async gen) │  │ _contexts: Dict[str, Ctx]   │ │ │
│  │  └─────────────┘  └──────┬──────┘  └─────────────────────────────┘ │ │
│  └──────────────────────────┼─────────────────────────────────────────┘ │
│                             │                                            │
│  ┌──────────────────────────▼─────────────────────────────────────────┐ │
│  │                      Workflow (workflow.py)                         │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────────┐  │ │
│  │  │ Node Parsing    │  │ Connection Graph │  │ Topological Sort  │  │ │
│  │  │ _parse_nodes()  │  │ connections_by_  │  │ get_execution_    │  │ │
│  │  │                 │  │ source/dest      │  │ order()           │  │ │
│  │  └─────────────────┘  └─────────────────┘  └────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                  ExecutionContext (context.py)                      │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐  │ │
│  │  │ session_id  │  │ chat_history│  │ node_outputs│  │ memory    │  │ │
│  │  │             │  │             │  │             │  │           │  │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └───────────┘  │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                      Node Executors (nodes/)                        │ │
│  │                                                                      │ │
│  │  Main Flow Nodes:                                                    │ │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                 │ │
│  │  │ ChatTrigger  │→│    Agent     │→│ConvertToFile │                 │ │
│  │  │ (entry)      │ │ (AI agent)   │ │ (file conv)  │                 │ │
│  │  └──────────────┘ └──────┬───────┘ └──────────────┘                 │ │
│  │                          │                                           │ │
│  │  AI Sub-nodes (attached to Agent):                                   │ │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────┐  │ │
│  │  │MemoryBuffer  │ │  ToolCode    │ │  DeepSeek    │ │OutputParser│  │ │
│  │  │ (memory)     │ │ (Python)     │ │ (LLM)        │ │ (parser)   │  │ │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
workflow/
├── __init__.py          # Package exports
├── models.py            # Data models and type definitions
├── workflow.py          # Workflow class - JSON parsing and graph building
├── context.py           # ExecutionContext - runtime state management
├── executor.py          # WorkflowExecutor - main execution engine
└── nodes/               # Node executors
    ├── __init__.py      # Executor registry
    ├── base.py          # BaseNodeExecutor abstract class
    ├── chat_trigger.py  # chatTrigger node
    ├── memory_buffer.py # memoryBufferWindow node
    ├── tool_code.py     # toolCode node (Python code execution)
    ├── output_parser.py # outputParserStructured node
    ├── convert_to_file.py # convertToFile node
    ├── agent.py         # agent node (AI Agent with tool calling)
    └── lm_deepseek.py   # lmChatDeepSeek node (DeepSeek LLM)
```

## Core Components

### 1. Data Models (`models.py`)

#### ConnectionType Enum

Defines the types of connections between nodes:

```python
class ConnectionType(str, Enum):
    MAIN = "main"                    # Primary data flow
    AI_TOOL = "ai_tool"              # Tool connections for agents
    AI_MEMORY = "ai_memory"          # Memory connections
    AI_LANGUAGE_MODEL = "ai_languageModel"  # LLM connections
    AI_OUTPUT_PARSER = "ai_outputParser"    # Output parser connections
```

#### Data Flow Models

```
NodeInput                          NodeOutput
┌─────────────────────┐            ┌─────────────────────┐
│ ports: [            │            │ ports: [            │
│   [                 │  execute() │   [                 │
│     [NodeData, ...],│ ────────→  │     NodeData, ...   │
│     [NodeData, ...] │            │   ]                 │
│   ]                 │            │ ]                   │
│ ]                   │            │                     │
└─────────────────────┘            └─────────────────────┘
  input_port → sources → items       output_port → items
```

| Class | Description |
|-------|-------------|
| `Node` | Node definition with id, name, type, parameters, credentials |
| `NodeData` | Data passed between nodes (json_data, binary_data, metadata) |
| `NodeInput` | Input structure: `ports[input_port][source][items]` |
| `NodeOutput` | Output structure: `ports[output_port][items]` |
| `NodeNotification` | Real-time notification sent to frontend |

#### NodeNotification

Used to send real-time progress updates to the frontend:

```python
@dataclass
class NodeNotification:
    node_name: str           # Node sending the notification
    session_id: str          # Session identifier
    message: str             # Text message
    html: str                # Optional HTML content
    notification_type: str   # "step" or "message"
```

### 2. Workflow Class (`workflow.py`)

Parses n8n workflow JSON and builds bidirectional connection graphs.

**Key Methods:**

| Method | Description |
|--------|-------------|
| `__init__(workflow_json)` | Parse nodes and connections from JSON |
| `get_start_node()` | Find the trigger node (entry point) |
| `get_parent_nodes(node_name, conn_type)` | Get upstream nodes |
| `get_child_nodes(node_name, conn_type)` | Get downstream nodes |
| `get_ai_sub_nodes(agent_name)` | Get AI sub-nodes for an agent |
| `get_execution_order()` | Topological sort for execution order |

**Connection Maps:**

```python
# Source perspective: where does data flow TO
connections_by_source[source_name][conn_type] = [[NodeConnection, ...], ...]

# Destination perspective: where does data come FROM
connections_by_destination[dest_name][conn_type] = [[SourceConnection, ...], ...]
```

### 3. ExecutionContext (`context.py`)

Manages runtime state during workflow execution.

**Key Attributes:**

```python
@dataclass
class ExecutionContext:
    session_id: str                              # Session identifier
    chat_history: List[Dict[str, str]]           # Conversation history
    files: List[Dict[str, Any]]                  # Uploaded files
    node_outputs: Dict[str, NodeOutput]          # Cached node outputs
    memory: Dict[str, List[Dict[str, str]]]      # Conversation memory
```

**Key Methods:**

| Method | Description |
|--------|-------------|
| `get_input_for_node()` | Gather inputs from parent nodes |
| `set_node_output()` | Store node execution result |
| `get_memory()` | Get conversation memory for a node |
| `add_to_memory()` | Add message to conversation memory |

### 4. WorkflowExecutor (`executor.py`)

Main execution engine that orchestrates workflow execution.

**Execution Flow:**

```
1. Load and parse workflow JSON
       ↓
2. Get execution order (topological sort)
       ↓
3. For each node in order:
   ├─ Get the appropriate NodeExecutor
   ├─ Gather input data from parent nodes
   ├─ Execute the node
   ├─ Store output for downstream nodes
   └─ Yield notification (for streaming)
       ↓
4. Return final result
```

**Key Methods:**

| Method | Description |
|--------|-------------|
| `from_json(workflow_json)` | Create executor from dict |
| `from_file(file_path)` | Create executor from JSON file |
| `execute(session_id, chat_history, files)` | Execute workflow (async generator) |
| `clear_context(session_id)` | Clear session context |

### 5. Node Executors (`nodes/`)

Each node type has its own executor class inheriting from `BaseNodeExecutor`.

#### Executor Registry

```python
NODE_EXECUTOR_REGISTRY = {
    "chatTrigger": ChatTriggerExecutor,
    "memoryBufferWindow": MemoryBufferExecutor,
    "toolCode": ToolCodeExecutor,
    "outputParserStructured": OutputParserExecutor,
    "convertToFile": ConvertToFileExecutor,
    "agent": AgentExecutor,
    "lmChatDeepSeek": DeepSeekExecutor,
}
```

#### Node Type Categories

| Category | Nodes | Execution |
|----------|-------|-----------|
| Main Flow | chatTrigger, agent, convertToFile | Direct `execute()` call |
| AI Sub-nodes | memory, tool, lm, parser | Called by Agent |

#### BaseNodeExecutor Methods

| Method | Description |
|--------|-------------|
| `execute(input_data, context)` | Execute node logic (override this) |
| `get_parameter(key, default)` | Get parameter from node config |
| `get_nested_parameter(path, default)` | Get nested parameter (dot notation) |
| `create_output(data)` | Create NodeOutput with single item |
| `get_notification(output, context)` | Get completion notification |
| `get_expression_value(expr, item, context)` | Evaluate n8n expression |

## Workflow Example

### NUS News ChatBot Execution Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│  ┌──────────────────┐                                                   │
│  │ When chat message│  chatInput: "Show me NUS news"                    │
│  │ received         │  sessionId: "user-123"                            │
│  └────────┬─────────┘                                                   │
│           │ main                                                         │
│           ▼                                                              │
│  ┌──────────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │  Analyze Agent   │←─│Simple Memory│  │ Code Tool   │                 │
│  │                  │  │(ai_memory)  │  │(ai_tool)    │                 │
│  │                  │←─└─────────────┘  └─────────────┘                 │
│  │                  │←─┌─────────────┐                                  │
│  │                  │  │Analyze Model│                                  │
│  │                  │  │(ai_lm)      │                                  │
│  └────────┬─────────┘  └─────────────┘                                  │
│           │ main                                                         │
│           ▼                                                              │
│  ┌──────────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │  Report Agent    │←─│Report Model │  │Output Parser│                 │
│  │                  │  │(ai_lm)      │  │(ai_parser)  │                 │
│  └────────┬─────────┘  └─────────────┘  └─────────────┘                 │
│           │ main                                                         │
│           ▼                                                              │
│  ┌──────────────────┐                                                   │
│  │ Convert to File  │  fileName: "NUS_News_Report.html"                 │
│  │                  │  mimeType: "text/html"                            │
│  └──────────────────┘                                                   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Usage

```python
from workflow import WorkflowExecutor

# Load workflow from file
executor = WorkflowExecutor.from_file("./NUS News ChatBot.json")

# Execute workflow (async generator)
async for notification in executor.execute(
    session_id="user-123",
    chat_history=[{"role": "user", "content": "Show me NUS news"}],
    files=[]
):
    print(notification.to_dict())
```

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DEEPSEEK_API_KEY` | API key for DeepSeek LLM | Yes |

## Extension Guide

### Adding a New Node Type

Follow these steps to add support for a new n8n node type:

#### Step 1: Create the Executor Class

Create a new file in `nodes/` directory:

```python
# nodes/my_node.py
"""
MyNode executor - description of what this node does.
"""

import logging
from typing import TYPE_CHECKING

from .base import BaseNodeExecutor
from ..models import NodeInput, NodeOutput, NodeNotification

if TYPE_CHECKING:
    from ..context import ExecutionContext

logger = logging.getLogger(__name__)


class MyNodeExecutor(BaseNodeExecutor):
    """
    Executor for myNode type.

    Parameters:
        - param1: Description of parameter 1
        - param2: Description of parameter 2

    Input:
        - Expects data with 'input_field' key

    Output:
        - Returns data with 'output_field' key
    """

    node_type = "myNode"

    async def execute(
        self,
        input_data: NodeInput,
        context: "ExecutionContext"
    ) -> NodeOutput:
        """Execute the node logic."""

        # 1. Get parameters from node configuration
        param1 = self.get_parameter("param1", default="default_value")
        param2 = self.get_nested_parameter("options.param2", default=None)

        # 2. Get input data
        input_json = input_data.first_json
        input_value = input_json.get("input_field", "")

        # 3. Process the data
        logger.info(f"[{self.node.name}] Processing: {input_value[:100]}...")
        result = self._process_data(input_value, param1, param2)

        # 4. Return output
        return self.create_output({
            "output_field": result,
            "metadata": {"processed": True}
        })

    def _process_data(self, input_value: str, param1: str, param2: str) -> str:
        """Internal processing logic."""
        # Implement your logic here
        return f"Processed: {input_value}"

    def get_notification(
        self,
        output: NodeOutput,
        context: "ExecutionContext"
    ) -> NodeNotification:
        """Return notification for frontend display."""
        return NodeNotification(
            node_name=self.node.name,
            session_id=context.session_id,
            message=f"MyNode completed processing",
            html="",  # Optional HTML content
            notification_type="step"
        )
```

#### Step 2: Register the Executor

Add the executor to the registry in `nodes/__init__.py`:

```python
from .my_node import MyNodeExecutor

NODE_EXECUTOR_REGISTRY = {
    # ... existing entries ...
    "myNode": MyNodeExecutor,
}

__all__ = [
    # ... existing entries ...
    "MyNodeExecutor",
]
```

#### Step 3: Add to Workflow JSON

Use the new node in your workflow JSON:

```json
{
    "nodes": [
        {
            "id": "unique-id",
            "name": "My Custom Node",
            "type": "@n8n/n8n-nodes-custom.myNode",
            "typeVersion": 1,
            "position": [400, 200],
            "parameters": {
                "param1": "value1",
                "options": {
                    "param2": "value2"
                }
            }
        }
    ],
    "connections": {
        "Previous Node": {
            "main": [[{"node": "My Custom Node", "type": "main", "index": 0}]]
        }
    }
}
```

### Adding a New AI Sub-node

AI sub-nodes (tools, memory, LLM, parser) are not executed directly. They provide capabilities to Agent nodes.

#### Example: Adding a New LLM Provider

```python
# nodes/lm_openai.py
"""
OpenAI LLM executor.
"""

from openai import AsyncOpenAI
from .base import BaseNodeExecutor
from ..models import NodeInput, NodeOutput

class OpenAIExecutor(BaseNodeExecutor):
    """Executor for OpenAI LLM."""

    node_type = "lmChatOpenAI"

    def __init__(self, node, workflow):
        super().__init__(node, workflow)
        self.client = AsyncOpenAI()
        self.model = self.get_parameter("model", "gpt-4")

    async def chat_completion(
        self,
        messages: list,
        tools: list = None,
        **kwargs
    ) -> dict:
        """Call OpenAI API for chat completion."""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            **kwargs
        )
        return response.choices[0].message
```

### Adding Expression Support

The engine supports n8n expression syntax. To add new expression patterns:

```python
# In base.py, extend get_expression_value()
def get_expression_value(self, expression: str, item: NodeData, context) -> Any:
    # ... existing code ...

    # Add new pattern: $context.session_id
    if expr.startswith("$context."):
        attr = expr[9:]
        return getattr(context, attr, None)

    # Add new pattern: $env.VARIABLE_NAME
    if expr.startswith("$env."):
        var_name = expr[5:]
        return os.environ.get(var_name)
```

## Design Decisions

### 1. LLM Integration

Uses OpenAI SDK to call DeepSeek API (OpenAI-compatible endpoint):

```python
from openai import OpenAI
client = OpenAI(api_key="...", base_url="https://api.deepseek.com")
```

### 2. Tool Code Execution

Follows n8n convention using `_query` global variable for input:

```python
# n8n Code Tool format
_query = "input string"
# ... code logic ...
return result
```

### 3. Connection Types

Supports multiple connection types for AI workflows:
- `main` - Primary data flow between nodes
- `ai_tool` - Tool definitions for agents
- `ai_memory` - Conversation memory
- `ai_languageModel` - LLM configuration
- `ai_outputParser` - Output parsing rules

### 4. Session Management

Each session has its own ExecutionContext, allowing multiple concurrent users:

```python
_contexts: Dict[str, ExecutionContext] = {}

def get_context(self, session_id: str) -> ExecutionContext:
    if session_id not in self._contexts:
        self._contexts[session_id] = ExecutionContext(session_id=session_id)
    return self._contexts[session_id]
```

## Testing

### Unit Testing a Node Executor

```python
import pytest
from workflow.models import Node, NodeInput, NodeData
from workflow.context import ExecutionContext
from workflow.nodes.my_node import MyNodeExecutor

@pytest.mark.asyncio
async def test_my_node_executor():
    # Create mock node
    node = Node(
        id="test-id",
        name="Test Node",
        type="@n8n/n8n-nodes-custom.myNode",
        type_version=1.0,
        position=(0, 0),
        parameters={"param1": "test_value"}
    )

    # Create executor
    executor = MyNodeExecutor(node, workflow=None)

    # Create input
    input_data = NodeInput(ports=[[[NodeData(json_data={"input_field": "test"})]]])
    context = ExecutionContext(session_id="test")

    # Execute
    output = await executor.execute(input_data, context)

    # Assert
    assert output.first_json.get("output_field") is not None
```

## Learning Resources

- [n8n GitHub Repository](https://github.com/n8n-io/n8n)
- Key n8n source files:
  - `packages/workflow/src/workflow.ts` - Workflow class
  - `packages/core/src/execution-engine/workflow-execute.ts` - Execution engine
- [FastAPI Streaming Responses](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)
- [OpenAI Python SDK](https://github.com/openai/openai-python)

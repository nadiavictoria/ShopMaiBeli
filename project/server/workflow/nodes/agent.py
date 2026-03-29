"""
AgentExecutor - handles agent node (AI agent with tools, memory, and language model).

Sub-nodes (tools, memory, language model, output parser) are instantiated and attached
to the agent node. The agent node is responsible for calling them during execution.
"""

import json
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from .base import BaseNodeExecutor
from ..models import NodeData, NodeInput, NodeNotification, NodeOutput, ConnectionType
from ..context import ExecutionContext

if TYPE_CHECKING:
    from .lm_deepseek import DeepSeekExecutor
    from .tool_code import ToolCodeExecutor
    from .memory_buffer import MemoryBufferExecutor
    from .output_parser import OutputParserExecutor

logger = logging.getLogger(__name__)


class AgentExecutor(BaseNodeExecutor):
    """
    Handles agent node - AI agent with tools, memory, and language model.

    Sub-nodes are instantiated and attached to the agent during execution.
    The agent calls sub-node methods directly instead of relying on pre-executed data.
    """

    node_type = "agent"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Sub-node instances (populated during execution)
        self.language_model: Optional["DeepSeekExecutor"] = None
        self.memory: Optional["MemoryBufferExecutor"] = None
        self.tools: List["ToolCodeExecutor"] = []
        self.output_parser: Optional["OutputParserExecutor"] = None
        self._sub_nodes_instantiated = False
        # Tool call records for notification
        self._tool_call_records: List[Dict[str, str]] = []

    def _instantiate_sub_nodes(self):
        """
        Instantiate all sub-nodes connected to this agent.
        Sub-nodes are attached to the agent and called directly during execution.
        """
        if self._sub_nodes_instantiated:
            return

        from .lm_deepseek import DeepSeekExecutor
        from .tool_code import ToolCodeExecutor
        from .memory_buffer import MemoryBufferExecutor
        from .output_parser import OutputParserExecutor

        # Get sub-node names from workflow connections
        sub_nodes = self.workflow.get_ai_sub_nodes(self.node.name)

        # Instantiate language model
        lm_names = sub_nodes.get(ConnectionType.AI_LANGUAGE_MODEL, [])
        if lm_names:
            lm_node = self.workflow.nodes.get(lm_names[0])
            if lm_node:
                self.language_model = DeepSeekExecutor(lm_node, self.workflow)

        # Instantiate memory
        memory_names = sub_nodes.get(ConnectionType.AI_MEMORY, [])
        if memory_names:
            memory_node = self.workflow.nodes.get(memory_names[0])
            if memory_node:
                self.memory = MemoryBufferExecutor(memory_node, self.workflow)

        # Instantiate tools
        tool_names = sub_nodes.get(ConnectionType.AI_TOOL, [])
        for tool_name in tool_names:
            tool_node = self.workflow.nodes.get(tool_name)
            if tool_node:
                self.tools.append(ToolCodeExecutor(tool_node, self.workflow))

        # Instantiate output parser
        parser_names = sub_nodes.get(ConnectionType.AI_OUTPUT_PARSER, [])
        if parser_names:
            parser_node = self.workflow.nodes.get(parser_names[0])
            if parser_node:
                self.output_parser = OutputParserExecutor(parser_node, self.workflow)

        self._sub_nodes_instantiated = True

    async def execute(
        self,
        input_data: NodeInput,
        context: ExecutionContext
    ) -> NodeOutput:
        # Instantiate all sub-nodes first
        self._instantiate_sub_nodes()

        # Get input items from port 0
        input_items = input_data.get_items(port=0)

        # Process each input item
        output_items = []
        for item in input_items:
            result = await self._execute_item(item, context)
            output_items.append(result)

        return NodeOutput.from_items(output_items)

    async def _execute_item(
        self,
        item: NodeData,
        context: ExecutionContext
    ) -> NodeData:
        """Process a single input item."""
        # Clear tool call records for this execution
        self._tool_call_records = []

        # Get agent configuration
        options = self.get_parameter("options", {})
        system_message = options.get("systemMessage", "You are a helpful assistant.")
        has_output_parser = self.get_parameter("hasOutputParser", False)

        # Get user input from item
        user_input = self._get_user_input(item, context)
        logger.info(f"[{self.node.name}] user_input: {user_input[:200]}..." if len(user_input) > 200 else f"[{self.node.name}] user_input: {user_input}")

        # Get memory messages directly from memory sub-node
        memory_messages = self._get_memory_messages(context)
        logger.info(f"[{self.node.name}] memory_messages ({len(memory_messages)} messages)")

        # Get tool definitions from tool sub-nodes
        tool_definitions = self._get_tool_definitions()
        logger.info(f"[{self.node.name}] tools: {[t.get('name', 'unknown') for t in tool_definitions]}")

        # Get output parser format instructions
        parser_instructions = None
        if has_output_parser and self.output_parser:
            parser_instructions = self.output_parser.get_format_instructions()

        # Build messages for the LLM
        messages = self._build_messages(
            system_message, memory_messages, user_input, parser_instructions
        )
        logger.info(f"[{self.node.name}] built messages ({len(messages)} total):")
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            content_preview = content[:100] + "..." if len(content) > 100 else content
            logger.info(f"  [{i}] {role}: {content_preview}")

        # Execute agent loop (memory is updated inside the loop)
        response = await self._run_agent_loop(
            messages=messages,
            tool_definitions=tool_definitions,
            context=context,
            user_input=user_input
        )

        # Parse output if parser is configured
        if has_output_parser and self.output_parser:
            parsed = self.output_parser.parse_output(response)
            output_data = {"output": parsed}
        else:
            output_data = {"output": response}

        return self.create_item(output_data)

    def _get_memory_messages(self, context: ExecutionContext) -> List[Dict[str, str]]:
        """Get memory messages from the memory sub-node."""
        if not self.memory:
            return []

        return self.memory.get_memory(context)

    def _add_to_memory(self, context: ExecutionContext, role: str, content: str):
        """Add a message to memory if memory sub-node is configured."""
        if not self.memory:
            return
        self.memory.add_to_memory(context, role, content)

    def _get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get tool definitions from tool sub-nodes."""
        return [tool.get_tool_definition() for tool in self.tools]

    def _get_user_input(
        self,
        item: NodeData,
        context: ExecutionContext,
    ) -> str:
        """
        Get user input based on promptType configuration.

        - If promptType is "define" and text template exists: evaluate the template
        - Otherwise: get chatInput from the previous node's output
        """
        prompt_type = self.get_parameter("promptType", "")
        text_template = self.get_parameter("text", "")

        if prompt_type == "define" and text_template:
            return self.get_expression_value(text_template, item, context) or ""

        # Default: get chatInput from item
        return str(item.json_data.get("chatInput", ""))

    def _build_messages(
        self,
        system_message: str,
        memory: List[Dict[str, str]],
        user_input: str,
        parser_instructions: Optional[str]
    ) -> List[Dict[str, str]]:
        """Build the message list for the LLM."""
        messages = []

        # Add memory (conversation history) first
        for msg in memory:
            messages.append(msg)

        # Check if first message is system, if not prepend system message
        system_content = system_message
        if parser_instructions:
            system_content += f"\n\n{parser_instructions}"

        if not messages or messages[0].get("role") != "system":
            messages.insert(0, {"role": "system", "content": system_content})

        # Add current user input
        messages.append({"role": "user", "content": user_input})

        return messages

    async def _run_agent_loop(
        self,
        messages: List[Dict[str, str]],
        tool_definitions: List[Dict[str, Any]],
        context: ExecutionContext,
        user_input: str,
        max_iterations: int = 10
    ) -> str:
        """
        Run the agent loop with tool calling support.

        The agent will:
        1. Call the LLM with the current messages
        2. If the LLM wants to use a tool, execute it and add the result
        3. Repeat until the LLM returns a final response or max iterations reached

        Memory is updated at each step of the loop.
        """
        if not self.language_model:
            return "Error: No language model configured for this agent."

        # Build tool name to executor mapping from attached tool sub-nodes
        tool_executors = {}
        for tool in self.tools:
            tool_name = tool.node.name.replace(" ", "_")
            tool_executors[tool_name] = tool

        current_messages = messages.copy()
        iteration = 0

        # Add user input to memory at the start
        self._add_to_memory(context, "user", user_input)

        while iteration < max_iterations:
            iteration += 1

            # Call LLM directly using the attached language model sub-node
            try:
                response = await self.language_model.chat_completion(
                    messages=current_messages,
                    tools=tool_definitions if tool_definitions else None,
                )
            except Exception as e:
                return f"Error calling language model: {str(e)}"

            # Check if LLM wants to use tools
            tool_calls = response.get("tool_calls", [])

            if not tool_calls:
                # No tool calls, return the response and add to memory
                final_response = response.get("content", "")
                logger.info(f"[{self.node.name}] LLM final response: {final_response[:200]}..." if len(final_response) > 200 else f"[{self.node.name}] LLM final response: {final_response}")
                self._add_to_memory(context, "assistant", final_response)
                return final_response

            # Process tool calls
            logger.info(f"[{self.node.name}] LLM requested tool calls: {[tc['name'] for tc in tool_calls]}")
            # Add assistant message with tool calls
            assistant_content = response.get("content", "")
            assistant_msg = {
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": tc["arguments"]
                        }
                    }
                    for tc in tool_calls
                ]
            }
            current_messages.append(assistant_msg)

            # Add assistant message to memory (with tool call info)
            tool_call_summary = ", ".join([tc["name"] for tc in tool_calls])
            memory_content = assistant_content if assistant_content else f"[Calling tools: {tool_call_summary}]"
            self._add_to_memory(context, "assistant", memory_content)

            # Execute each tool using attached tool sub-nodes
            for tc in tool_calls:
                tool_name = tc["name"]
                tool_args = tc["arguments"]

                try:
                    args_dict = json.loads(tool_args)
                    query = args_dict.get("_query", "")
                except json.JSONDecodeError:
                    query = tool_args

                # Execute the tool directly using the attached sub-node
                if tool_name in tool_executors:
                    logger.info(f"[{self.node.name}] executing tool '{tool_name}' with query: {query[:100]}..." if len(query) > 100 else f"[{self.node.name}] executing tool '{tool_name}' with query: {query}")
                    tool_result = await tool_executors[tool_name].execute_tool(query, context)
                    logger.info(f"[{self.node.name}] tool '{tool_name}' result: {tool_result[:200]}..." if len(tool_result) > 200 else f"[{self.node.name}] tool '{tool_name}' result: {tool_result}")
                else:
                    tool_result = f"Error: Tool '{tool_name}' not found."
                    logger.warning(f"[{self.node.name}] tool '{tool_name}' not found in executors")

                # Record tool call for notification (full result, no truncation)
                self._tool_call_records.append({
                    "tool": tool_name,
                    "query": query,
                    "result": tool_result,
                })

                # Add tool result message
                current_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result,
                })

                # Add tool result to memory
                self._add_to_memory(context, "tool", f"[{tool_name}]: {tool_result[:500]}")

        return "Error: Maximum iterations reached without final response."

    def _format_tool_result_html(self, result: str) -> str:
        """Format tool result as HTML. If result is JSON list of dicts, render as table."""
        try:
            data = json.loads(result)
            # Check if it's a dict with 'items' key containing a list
            if isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
                items = data["items"]
                if items and isinstance(items[0], dict):
                    return self._render_table(items)
            # Check if it's directly a list of dicts
            if isinstance(data, list) and data and isinstance(data[0], dict):
                return self._render_table(data)
            # Otherwise render as formatted JSON
            return f'<pre style="margin:0;white-space:pre-wrap;word-break:break-all;">{json.dumps(data, indent=2, ensure_ascii=False)}</pre>'
        except (json.JSONDecodeError, TypeError):
            # Plain text result
            return f'<pre style="margin:0;white-space:pre-wrap;word-break:break-all;">{result}</pre>'

    def _render_table(self, items: List[Dict[str, Any]]) -> str:
        """Render a list of dicts as an HTML table."""
        if not items:
            return "<p>No items</p>"

        # Get all unique keys from all items
        keys = []
        for item in items:
            for key in item.keys():
                if key not in keys:
                    keys.append(key)

        html = '''<table style="border-collapse:collapse;width:100%;font-size:12px;">
<thead><tr style="background:#f5f5f5;">'''
        for key in keys:
            html += f'<th style="border:1px solid #ddd;padding:6px;text-align:left;">{key}</th>'
        html += '</tr></thead><tbody>'

        for item in items:
            html += '<tr>'
            for key in keys:
                value = item.get(key, "")
                # Truncate long values in table cells
                display_value = str(value)
                if len(display_value) > 100:
                    display_value = display_value[:100] + "..."
                html += f'<td style="border:1px solid #ddd;padding:6px;">{display_value}</td>'
            html += '</tr>'

        html += '</tbody></table>'
        return html

    def get_notification(
        self, output: NodeOutput, context: ExecutionContext
    ) -> Optional[NodeNotification]:
        """Send notification with agent response and tool call results as complete HTML document."""
        response = ""
        if output.first_item:
            response = output.first_item.json_data.get("output", "")

        # Build complete HTML document with tool call results
        html_parts = ['''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Agent Tool Calls</title>
  <style>
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      margin: 0;
      padding: 20px;
      background: #fff;
      color: #333;
      line-height: 1.5;
    }
    h2 { margin: 0 0 20px 0; color: #222; font-size: 18px; }
    .tool-card {
      margin-bottom: 16px;
      border: 1px solid #e0e0e0;
      border-radius: 6px;
      overflow: hidden;
      background: #fff;
    }
    .tool-header {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      padding: 10px 14px;
      font-weight: 600;
      color: #fff;
      font-size: 14px;
    }
    .tool-body { padding: 14px; }
    .section-label {
      color: #666;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 6px;
    }
    .query-box, .result-box {
      background: #f8f9fa;
      border-radius: 4px;
      padding: 10px;
      margin-bottom: 12px;
    }
    .query-box:last-child, .result-box:last-child { margin-bottom: 0; }
    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-all;
      font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
      font-size: 12px;
    }
    table {
      border-collapse: collapse;
      width: 100%;
      font-size: 12px;
    }
    th, td {
      border: 1px solid #ddd;
      padding: 8px 10px;
      text-align: left;
    }
    th {
      background: #f0f0f0;
      font-weight: 600;
      color: #555;
    }
    tr:nth-child(even) { background: #fafafa; }
    tr:hover { background: #f5f5f5; }
    .no-tools { color: #888; font-style: italic; }
  </style>
</head>
<body>
  <h2>Tool Calls</h2>
''']

        if self._tool_call_records:
            for i, record in enumerate(self._tool_call_records, 1):
                tool_name = record["tool"]
                query = record["query"]
                result = record["result"]

                html_parts.append(f'''  <div class="tool-card">
    <div class="tool-header">{i}. {tool_name}</div>
    <div class="tool-body">
      <div class="section-label">Query</div>
      <div class="query-box"><pre>{query}</pre></div>
      <div class="section-label">Result</div>
      <div class="result-box">{self._format_tool_result_html(result)}</div>
    </div>
  </div>
''')
        else:
            html_parts.append('  <p class="no-tools">No tool calls were made.</p>\n')

        html_parts.append('''</body>
</html>''')

        html = "".join(html_parts)

        # Truncate message for display
        display_text = response[:200] + "..." if len(response) > 200 else response

        return NodeNotification(
            node_name=self.node.name,
            session_id=context.session_id,
            message=display_text,
            html=html,
        )

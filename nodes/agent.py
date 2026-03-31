import logging
from workflow_engine.models import NodeInput, NodeOutput, NodeNotification
from .base import BaseNodeExecutor

logger = logging.getLogger(__name__)


class AgentExecutor(BaseNodeExecutor):
    node_type = "agent"

    def _get_sub_executor(self, sub_type: str):
        if not self.workflow:
            return None
        sub_nodes = self.workflow.get_sub_nodes(self.node.name)
        for name, sub_node in sub_nodes.items():
            if sub_node.node_type == sub_type:
                from nodes import get_executor_class
                return get_executor_class(sub_node.node_type)(sub_node, self.workflow)
        return None

    async def execute(self, input_data: NodeInput, context) -> NodeOutput:
        from nodes.lm_deepseek import DeepSeekExecutor
        from nodes.memory_buffer import MemoryBufferExecutor
        from nodes.output_parser import OutputParserExecutor

        system_message = self.get_parameter("options", {}).get("systemMessage", "")
        has_output_parser = self.get_parameter("hasOutputParser", False)

        lm_executor = self._get_sub_executor("lmChatDeepSeek")
        memory_executor = self._get_sub_executor("memoryBufferWindow")
        parser_executor = self._get_sub_executor("outputParserStructured")

        if has_output_parser and parser_executor:
            fmt = parser_executor.get_format_instructions()
            if fmt:
                system_message = f"{system_message}\n\n{fmt}"

        input_json = input_data.first_json
        user_message = input_json.get("chatInput", "") or input_json.get("output", "") or str(input_json)

        messages = []
        if memory_executor:
            messages = memory_executor.get_messages(context)
        messages.append({"role": "user", "content": user_message})

        if lm_executor and isinstance(lm_executor, DeepSeekExecutor):
            response = await lm_executor.chat_completion(messages, system_prompt=system_message)
        else:
            response = f"[No LLM configured for agent '{self.node.name}']"

        if memory_executor:
            memory_executor.add_message(context, "user", user_message)
            memory_executor.add_message(context, "assistant", response)

        if has_output_parser and parser_executor:
            return self.create_output(parser_executor.parse(response))

        return self.create_output({"output": response})

    def get_notification(self, output: NodeOutput, context) -> NodeNotification:
        return NodeNotification(
            node_name=self.node.name,
            session_id=context.session_id,
            message=f"Agent '{self.node.name}' completed",
            notification_type="step",
            data=output.first_json
        )

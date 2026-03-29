"""
ChatTriggerExecutor - handles chatTrigger node (entry point for chat workflows).
"""

import logging
from typing import Optional

from .base import BaseNodeExecutor
from ..models import NodeInput, NodeNotification, NodeOutput
from ..context import ExecutionContext

logger = logging.getLogger(__name__)


class ChatTriggerExecutor(BaseNodeExecutor):
    """
    Handles chatTrigger node - entry point for chat workflows.
    Extracts the latest user message from chat_history and passes it to the workflow.
    """

    node_type = "chatTrigger"

    async def execute(
        self,
        input_data: NodeInput,
        context: ExecutionContext
    ) -> NodeOutput:
        # Log chat history
        logger.info(f"[ChatTrigger] session_id={context.session_id}")
        logger.info(f"[ChatTrigger] chat_history ({len(context.chat_history)} messages):")
        for i, msg in enumerate(context.chat_history):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            content_preview = content[:200] + "..." if len(content) > 200 else content
            logger.info(f"  [{i}] {role}: {content_preview}")

        # Get the latest user message from chat history
        user_message = ""
        if context.chat_history:
            for msg in reversed(context.chat_history):
                if msg.get("role") == "user":
                    user_message = msg.get("content", "")
                    break

        logger.info(f"[ChatTrigger] extracted user_message: {user_message[:200]}..." if len(user_message) > 200 else f"[ChatTrigger] extracted user_message: {user_message}")

        return self.create_output({
            "chatInput": user_message,
            "sessionId": context.session_id,
        })

    def get_notification(
        self, output: NodeOutput, context: ExecutionContext
    ) -> Optional[NodeNotification]:
        """Return notification with received user message."""
        user_message = ""
        if output.first_item:
            user_message = output.first_item.json_data.get("chatInput", "")

        display_msg = f"Received: {user_message[:200]}..." if len(user_message) > 200 else f"Received: {user_message}"

        return NodeNotification(
            node_name=self.node.name,
            session_id=context.session_id,
            message=display_msg,
        )

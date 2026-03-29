"""
ConvertToFileExecutor - handles convertToFile node.
"""

import base64
import logging
from typing import Optional

from .base import BaseNodeExecutor
from ..models import NodeData, NodeInput, NodeNotification, NodeOutput
from ..context import ExecutionContext

logger = logging.getLogger(__name__)


class ConvertToFileExecutor(BaseNodeExecutor):
    """
    Handles convertToFile node - converts data to file format.
    """

    node_type = "convertToFile"

    async def execute(
        self,
        input_data: NodeInput,
        context: ExecutionContext
    ) -> NodeOutput:
        # Get first input item
        item = input_data.first_item
        if not item:
            return NodeOutput.single({"error": "No input data"})

        result = self._process_item(item)
        return NodeOutput.from_item(result)

    def _process_item(self, item: NodeData) -> NodeData:
        """Process a single input item."""
        operation = self.get_parameter("operation", "toText")
        source_property = self.get_parameter("sourceProperty", "")
        options = self.get_parameter("options", {})
        file_name = options.get("fileName", "output.txt")

        logger.info(f"[{self.node.name}] operation={operation}, source_property={source_property}, file_name={file_name}")

        # Get source data from item
        json_data = item.json_data
        logger.info(f"[{self.node.name}] input json_data keys: {list(json_data.keys()) if isinstance(json_data, dict) else type(json_data)}")

        # Navigate to source property (e.g., "output.html")
        for key in source_property.split("."):
            if isinstance(json_data, dict):
                json_data = json_data.get(key, "")
            else:
                break
        source_data = str(json_data) if json_data else ""

        logger.info(f"[{self.node.name}] extracted source_data: {source_data[:200]}..." if len(source_data) > 200 else f"[{self.node.name}] extracted source_data: {source_data}")

        if operation == "toText":
            # Convert to binary and encode as base64
            raw_binary = source_data.encode("utf-8")
            binary_data = base64.b64encode(raw_binary)

            # Determine MIME type
            if file_name.endswith(".html"):
                mime_type = "text/html"
            elif file_name.endswith(".json"):
                mime_type = "application/json"
            elif file_name.endswith(".csv"):
                mime_type = "text/csv"
            else:
                mime_type = "text/plain"

            # Store in NodeData fields
            output_json = {
                "fileName": file_name,
                "mimeType": mime_type,
                "fileSize": len(raw_binary),
                "html": source_data if mime_type == "text/html" else "",
            }

            return NodeData(
                json_data=output_json,
                binary_data=binary_data,
            )
        else:
            return NodeData(json_data={"error": f"Unsupported operation: {operation}"})

    def get_notification(
        self, output: NodeOutput, context: ExecutionContext
    ) -> Optional[NodeNotification]:
        """Return notification with file conversion result."""
        if not output.first_item:
            return None

        data = output.first_item.json_data
        if "error" in data:
            return NodeNotification(
                node_name=self.node.name,
                session_id=context.session_id,
                message=data["error"],
            )
        else:
            file_name = data.get("fileName", "unknown")
            html = data.get("html", "")
            return NodeNotification(
                node_name=self.node.name,
                session_id=context.session_id,
                message=f"Converted to {file_name}",
                html="",
            )

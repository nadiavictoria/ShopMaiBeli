"""
OutputParserExecutor - handles outputParserStructured node.

This is an AI sub-node that provides output parsing to agent nodes.
It is not executed directly in the main flow.
"""

import json
import re
from typing import Dict, Any
from .base import BaseNodeExecutor


class OutputParserExecutor(BaseNodeExecutor):
    """
    Handles outputParserStructured node - parses agent output into structured format.

    This node is not executed in the main flow. Instead, agent nodes
    access it to get format instructions and parse outputs.
    """

    node_type = "outputParserStructured"

    def get_schema(self) -> Dict[str, Any]:
        """
        Get the JSON schema for structured output.

        Returns:
            Parsed JSON schema dict
        """
        schema_example = self.get_parameter("jsonSchemaExample", "{}")
        try:
            return json.loads(schema_example)
        except json.JSONDecodeError:
            return {}

    def parse_output(self, text: str) -> dict:
        """Parse the agent output according to the schema."""
        try:
            # Try to extract JSON from the text
            # Handle markdown code blocks
            if "```json" in text:
                match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
                if match:
                    text = match.group(1).strip()
            elif "```" in text:
                match = re.search(r"```\s*([\s\S]*?)\s*```", text)
                if match:
                    text = match.group(1).strip()

            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}

    def get_format_instructions(self) -> str:
        """Get format instructions for the LLM based on the schema."""
        schema_example = self.get_parameter("jsonSchemaExample", "{}")
        return f"""\n\nYou must respond with a valid JSON object that matches this schema:
{schema_example}

Do not include any text before or after the JSON. Do not use markdown code blocks."""

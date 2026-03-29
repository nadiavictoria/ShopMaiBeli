"""
Utility functions for workflow structure formatting.
"""

import json


def build_n8n_demo_html(workflow: dict) -> str:
    """
    Build markdown-style text representation of the workflow structure.

    This is displayed as plain text in Chainlit (no HTML rendering needed).

    Args:
        workflow: The n8n workflow JSON object

    Returns:
        Markdown-formatted string with workflow visualization
    """
    workflow_name = workflow.get("name", "Unnamed Workflow")
    nodes = workflow.get("nodes", [])
    connections = workflow.get("connections", {})

    # Count connections
    connection_count = 0
    for source, types in connections.items():
        for conn_type, outputs in types.items():
            for output_list in outputs:
                connection_count += len(output_list)

    # Build markdown
    markdown = f"""# ⚡ {workflow_name}

**Workflow Execution Pipeline**

---

## 📊 Summary
- **Nodes:** {len(nodes)}
- **Connections:** {connection_count}

---

## 📦 Nodes

"""

    for node in nodes:
        node_name = node.get("name", "Unknown")
        node_type = node.get("type", "").split(".")[-1]
        markdown += f"- **{node_name}** `{node_type}`\n"

    markdown += "\n---\n\n## 🔗 Connections\n\n"

    # Build connections list
    has_connections = False
    for source, types in connections.items():
        for conn_type, outputs in types.items():
            for output_list in outputs:
                for conn in output_list:
                    target = conn.get("node", "Unknown")
                    markdown += f"- {source} → **{target}**\n"
                    has_connections = True

    if not has_connections:
        markdown += "- *(No connections)*\n"

    return markdown

"""Utility to generate n8n workflow visualization HTML."""
import json


def generate_n8n_html(workflow: dict, editable: bool = False) -> str:
    workflow_json = json.dumps(workflow, indent=2)
    nodes = workflow.get("nodes", [])

    nodes_html = ""
    x_offset = 100
    for i, node in enumerate(nodes):
        node_type = node.get("type", "").split(".")[-1]
        color = _node_color(node_type)
        x = x_offset + i * 220
        nodes_html += f"""
        <div class="n8n-node" style="left:{x}px; top:150px; background:{color};">
            <div class="node-title">{node['name']}</div>
            <div class="node-type">{node_type}</div>
        </div>
        """

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>ShopMaiBeli Workflow</title>
<style>
body {{ font-family: sans-serif; background: #1a1a2e; color: #eee; margin: 0; padding: 20px; }}
h2 {{ color: #7dd3fc; }}
.workflow-canvas {{ position: relative; width: 100%; height: 400px; background: #16213e; border-radius: 12px; overflow: auto; }}
.n8n-node {{ position: absolute; padding: 12px 16px; border-radius: 8px; min-width: 160px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }}
.node-title {{ font-weight: 700; font-size: 14px; margin-bottom: 4px; }}
.node-type {{ font-size: 11px; opacity: 0.7; text-transform: uppercase; }}
pre {{ background: #0f3460; padding: 16px; border-radius: 8px; overflow: auto; font-size: 12px; }}
</style>
</head>
<body>
<h2>Workflow: {workflow.get('name', 'ShopMaiBeli')}</h2>
<div class="workflow-canvas">{nodes_html}</div>
<h3>Workflow JSON</h3>
<pre>{workflow_json}</pre>
</body>
</html>"""


def _node_color(node_type: str) -> str:
    colors = {
        "chatTrigger": "#166534",
        "agent": "#1e40af",
        "productSearch": "#065f46",
        "reviewAnalyzer": "#92400e",
        "convertToFile": "#581c87",
        "lmChatDeepSeek": "#0c4a6e",
        "memoryBufferWindow": "#4c1d95",
        "outputParserStructured": "#7f1d1d",
    }
    return colors.get(node_type, "#374151")

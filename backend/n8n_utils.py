"""
Utility functions for workflow structure formatting.
"""

import json


def build_n8n_demo_html(workflow: dict) -> str:
    """
    Build a full HTML page embedding the n8n-demo web component to visualize
    the workflow as an interactive graph.

    Args:
        workflow: The n8n workflow JSON object

    Returns:
        Full HTML document string for rendering in an iframe
    """
    # Serialize workflow JSON — single-quoted HTML attribute, so no escaping needed
    # (JSON strings use double quotes; single quotes never appear in valid JSON)
    workflow_json = json.dumps(workflow, ensure_ascii=False)
    # Escape any single quotes that may appear in string values
    workflow_json_escaped = workflow_json.replace("'", "&#39;")

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{workflow.get('name', 'Workflow Preview')}</title>
  <script src="https://cdn.jsdelivr.net/npm/@webcomponents/webcomponentsjs@2.0.0/webcomponents-loader.js"></script>
  <script src="https://www.unpkg.com/lit@2.0.0-rc.2/polyfill-support.js"></script>
  <script type="module" src="https://cdn.jsdelivr.net/npm/@n8n_io/n8n-demo-component/n8n-demo.bundled.js"></script>
  <style>
    html, body {{ height: 100%; margin: 0; font-family: system-ui, -apple-system, sans-serif; background: #f5f5f5; }}
    .container {{ height: 100%; padding: 12px; box-sizing: border-box; display: flex; flex-direction: column; gap: 8px; }}
    .header {{ font-size: 14px; font-weight: 600; color: #333; padding: 4px 0; }}
    .panel {{ flex: 1; border: 1px solid #ddd; border-radius: 8px; background: #fff; overflow: hidden; }}
    n8n-demo {{ width: 100%; height: 100%; display: block; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">⚡ {workflow.get('name', 'Workflow Preview')}</div>
    <div class="panel">
      <n8n-demo workflow='{workflow_json_escaped}'></n8n-demo>
    </div>
  </div>
</body>
</html>"""

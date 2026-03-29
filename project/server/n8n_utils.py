"""
Utility functions for n8n workflow HTML generation.
"""

import json
import html


def build_n8n_demo_html(workflow: dict) -> str:
    """
    Build HTML page with n8n-demo component for workflow visualization.

    Args:
        workflow: The n8n workflow JSON object

    Returns:
        Complete HTML string with embedded workflow
    """
    workflow_json = json.dumps(workflow, ensure_ascii=False)
    workflow_attr = html.escape(workflow_json, quote=True)
    return f"""<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>n8n-demo Test</title>

  <script src="https://cdn.jsdelivr.net/npm/@webcomponents/webcomponentsjs@2.0.0/webcomponents-loader.js"></script>
  <script src="https://www.unpkg.com/lit@2.0.0-rc.2/polyfill-support.js"></script>
  <script type="module" src="https://cdn.jsdelivr.net/npm/@n8n_io/n8n-demo-component/n8n-demo.bundled.js"></script>

  <style>
    html, body {{ height: 100%; margin: 0; font-family: system-ui, sans-serif; }}
    .wrap {{ height: 100%; padding: 0; box-sizing: border-box; }}
    .panel {{ height: 100%; box-sizing: border-box; overflow: auto; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="panel">
      <n8n-demo workflow="{workflow_attr}" tidyup="true"></n8n-demo>
    </div>
  </div>

  <script>
    // Bypass IntersectionObserver lazy-loading issue (observer may not detect visibility in nested iframes)
    let workflowLoaded = false;
    let forceLoadDone = false;
    let buttonClicked = false;

    function forceLoadN8nDemo() {{
      if (forceLoadDone) return true;

      const demo = document.querySelector('n8n-demo');
      if (!demo) return false;

      const shadowRoot = demo.shadowRoot;
      if (!shadowRoot) return false;

      const iframe = shadowRoot.getElementById('int_iframe') || shadowRoot.querySelector('iframe');
      if (!iframe) return false;

      // Re-register observer if it exists
      if (demo.observer && iframe) {{
        demo.observer.observe(iframe);
      }}

      // Force visibility and load (only once)
      demo.iframeVisible = true;
      if (typeof demo.loadWorkflow === 'function') {{
        demo.loadWorkflow();
      }}

      forceLoadDone = true;
      return true;
    }}

    function clickShowButton() {{
      if (buttonClicked) return true;

      const demo = document.querySelector('n8n-demo');
      if (!demo || !demo.shadowRoot) return false;

      const btn = demo.shadowRoot.querySelector('button');
      if (btn && btn.offsetParent !== null) {{
        btn.click();
        buttonClicked = true;
        return true;
      }}
      return false;
    }}

    // Poll until workflow is fully loaded
    function waitAndLoad() {{
      if (workflowLoaded) return;

      let attempts = 0;
      const maxAttempts = 100;

      const interval = setInterval(() => {{
        attempts++;

        forceLoadN8nDemo();
        clickShowButton();

        // Stop polling once both actions are done
        if ((forceLoadDone && buttonClicked) || attempts >= maxAttempts) {{
          workflowLoaded = true;
          clearInterval(interval);
        }}
      }}, 100);
    }}

    // Start polling after page load
    if (document.readyState === 'complete') {{
      waitAndLoad();
    }} else {{
      window.addEventListener('load', waitAndLoad);
    }}

    // Re-trigger when user opens HTML Preview
    document.addEventListener('visibilitychange', () => {{
      if (document.visibilityState === 'visible' && !workflowLoaded) {{
        waitAndLoad();
      }}
    }});

    window.addEventListener('focus', () => {{
      if (!workflowLoaded) waitAndLoad();
    }});
  </script>
</body>
</html>"""

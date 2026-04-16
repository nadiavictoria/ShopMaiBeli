"""
Utility functions for workflow structure formatting.
"""

import json


def build_n8n_demo_html(workflow: dict, backend_url: str = "http://localhost:8888") -> str:
    """
    Build a full HTML page with an interactive, editable workflow graph editor.

    Users can:
    - Drag nodes to reposition them
    - Add new nodes from the palette
    - Delete nodes (× button)
    - Draw connections by dragging from an output port to an input port
    - Click a connection arrow to delete it
    - Click ▶ Run to execute the (possibly modified) workflow

    Args:
        workflow: The n8n-compatible workflow JSON object
        backend_url: The backend base URL for the Run button

    Returns:
        Full self-contained HTML document string for rendering in an iframe
    """
    # Serialize workflow JSON for safe JavaScript embedding.
    # ensure_ascii=True avoids encoding issues; replace </ to prevent </script> injection.
    wf_json = json.dumps(workflow, ensure_ascii=True).replace("</", "<\\/")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Edit Workflow</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:system-ui,-apple-system,sans-serif;height:100vh;overflow:hidden;background:#f0f2f5;display:flex;flex-direction:column}}
#toolbar{{display:flex;align-items:center;gap:6px;padding:7px 10px;background:#fff;border-bottom:1px solid #e2e8f0;flex-shrink:0;flex-wrap:wrap}}
#wf-name{{font-weight:600;font-size:13px;color:#1e293b;margin-right:4px}}
.add-btn{{padding:3px 8px;border-radius:4px;border:1px solid #cbd5e1;background:#fff;font-size:11px;cursor:pointer;white-space:nowrap}}
.add-btn:hover{{background:#f8fafc;border-color:#94a3b8}}
#run-btn{{padding:5px 13px;border-radius:6px;background:#10b981;color:#fff;border:none;cursor:pointer;font-size:12px;font-weight:700;margin-left:auto}}
#run-btn:hover{{background:#059669}}
#run-btn:disabled{{background:#94a3b8;cursor:not-allowed}}
#copy-btn{{padding:5px 10px;border-radius:6px;background:#f1f5f9;border:1px solid #cbd5e1;cursor:pointer;font-size:11px}}
#copy-btn:hover{{background:#e2e8f0}}
#canvas-wrap{{flex:1;overflow:auto;position:relative;background:#f8fafc;background-image:radial-gradient(#d1d5db 1px,transparent 1px);background-size:20px 20px}}
#canvas-inner{{position:relative;width:2400px;height:1400px}}
#svg-layer{{position:absolute;top:0;left:0;width:100%;height:100%;overflow:visible}}
#svg-layer path{{pointer-events:visibleStroke;cursor:pointer}}
.node{{position:absolute;width:182px;background:#fff;border-radius:8px;border:1px solid #e2e8f0;box-shadow:0 2px 8px rgba(0,0,0,.09);user-select:none;z-index:10}}
.node-header{{padding:7px 8px;border-radius:7px 7px 0 0;display:flex;align-items:center;justify-content:space-between;cursor:grab;color:#fff;font-size:11px;font-weight:700}}
.node-header:active{{cursor:grabbing}}
.node-title{{display:flex;align-items:center;gap:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0}}
.node-del{{background:transparent;border:none;color:rgba(255,255,255,.7);cursor:pointer;font-size:15px;line-height:1;padding:0 2px;flex-shrink:0}}
.node-del:hover{{color:#fff}}
.node-body{{padding:5px 10px 8px;font-size:10px;color:#64748b;position:relative;min-height:32px}}
.port{{position:absolute;width:13px;height:13px;border-radius:50%;background:#6366f1;border:2px solid #fff;box-shadow:0 0 0 1.5px #6366f1;top:50%;transform:translateY(-50%);cursor:crosshair;z-index:20}}
.port-in{{left:-8px}}
.port-out{{right:-8px}}
.port-out:hover{{background:#4f46e5;transform:translateY(-50%) scale(1.25)}}
#output-panel{{flex-shrink:0;background:#fff;border-top:1px solid #e2e8f0;display:none;flex-direction:column;max-height:220px}}
#output-header{{padding:5px 12px;font-size:11px;font-weight:700;color:#475569;background:#f8fafc;border-bottom:1px solid #e2e8f0;display:flex;justify-content:space-between;align-items:center;flex-shrink:0}}
#output-content{{padding:8px 12px;font-size:11px;white-space:pre-wrap;color:#1e293b;overflow-y:auto;flex:1}}
</style>
</head>
<body>
<div id="toolbar">
  <span id="wf-name"></span>
  <div id="palette"></div>
  <button id="copy-btn">&#123;&#125; JSON</button>
  <button id="run-btn">&#9654; Run</button>
</div>
<div id="canvas-wrap">
  <div id="canvas-inner">
    <svg id="svg-layer"></svg>
  </div>
</div>
<div id="output-panel">
  <div id="output-header">
    <span>Execution Output</span>
    <button onclick="closeOutput()" style="background:none;border:none;cursor:pointer;color:#94a3b8;font-size:14px">&#10005;</button>
  </div>
  <div id="output-content"></div>
</div>

<script>
const WORKFLOW = {wf_json};
const BACKEND_URL = {json.dumps(backend_url)};

const NODE_TYPES = {{
  chatTrigger:    {{label:'Chat Trigger',   color:'#ff6d5a',icon:'&#128172;',in:0,out:1}},
  agent:          {{label:'AI Agent',        color:'#6366f1',icon:'&#129302;',in:1,out:1}},
  productSearch:  {{label:'Product Search',  color:'#3b82f6',icon:'&#128269;',in:1,out:1}},
  reviewAnalyzer: {{label:'Review Analyzer', color:'#10b981',icon:'&#11088;', in:1,out:1}},
  convertToFile:  {{label:'Convert to File', color:'#8b5cf6',icon:'&#128196;',in:1,out:0}},
}};

// ── State ────────────────────────────────────────────────────────────────────
let nodes = {{}};    // id → {{id,name,type,x,y,parameters}}
let edges = [];     // editable main-flow edges: [{{from:id, to:id}}]
let auxEdges = [];  // preserved non-main edges: [{{from:id, to:id, connType:string}}]
let nxtId = 1;
let drag  = null;   // {{nodeId,mx0,my0,nx0,ny0}}
let conn  = null;   // {{fromId,mx,my}}

// ── Init ─────────────────────────────────────────────────────────────────────
function init() {{
  document.getElementById('wf-name').textContent = WORKFLOW.name || 'Workflow';

  const nameToId = {{}};
  (WORKFLOW.nodes || []).forEach(n => {{
    const id = 'n' + (nxtId++);
    const [rx, ry] = n.position || [100, 100];
    nodes[id] = {{id, name:n.name, type:n.type, x:rx+60, y:ry+60, parameters:n.parameters||{{}}}};
    nameToId[n.name] = id;
  }});

  Object.entries(WORKFLOW.connections || {{}}).forEach(([fromName, types]) => {{
    const fid = nameToId[fromName]; if (!fid) return;
    Object.entries(types || {{}}).forEach(([connType, outputs]) => {{
      (outputs || []).forEach(list => (list || []).forEach(c => {{
        const tid = nameToId[c.node]; if (!tid) return;
        if (connType === 'main') {{
          edges.push({{from:fid,to:tid}});
        }} else {{
          auxEdges.push({{from:fid,to:tid,connType}});
        }}
      }}));
    }});
  }});

  const palette = document.getElementById('palette');
  Object.entries(NODE_TYPES).forEach(([type, cfg]) => {{
    const btn = document.createElement('button');
    btn.className = 'add-btn';
    btn.innerHTML = '+ ' + cfg.icon + ' ' + cfg.label;
    btn.onclick = () => addNode(type);
    palette.appendChild(btn);
  }});

  render();
  setupEvents();
}}

// ── Geometry ─────────────────────────────────────────────────────────────────
const NW = 182, NH = 64;

function outPt(id) {{ const n=nodes[id]; return {{x:n.x+NW+6, y:n.y+NH/2}}; }}
function inPt(id)  {{ const n=nodes[id]; return {{x:n.x-6,    y:n.y+NH/2}}; }}

function bezier(x1,y1,x2,y2) {{
  const cx = Math.max(60, Math.abs(x2-x1)*0.45);
  return `M${{x1}},${{y1}} C${{x1+cx}},${{y1}} ${{x2-cx}},${{y2}} ${{x2}},${{y2}}`;
}}

// ── Render ───────────────────────────────────────────────────────────────────
function render() {{ renderNodes(); renderEdges(); }}

function renderNodes() {{
  const canvas = document.getElementById('canvas-inner');
  canvas.querySelectorAll('.node').forEach(el => el.remove());
  Object.values(nodes).forEach(n => {{
    const cfg = NODE_TYPES[n.type] || {{label:n.type,color:'#64748b',icon:'&#9881;',in:1,out:1}};
    const el = document.createElement('div');
    el.className = 'node'; el.id = 'node-'+n.id;
    el.style.left = n.x+'px'; el.style.top = n.y+'px';
    el.innerHTML =
      `<div class="node-header" style="background:${{cfg.color}}" data-drag="${{n.id}}">
         <span class="node-title">${{cfg.icon}} ${{n.name}}</span>
         <button class="node-del" data-del="${{n.id}}">&#215;</button>
       </div>
       <div class="node-body">
         <span>${{cfg.label}}</span>
         ${{cfg.in  ? `<div class="port port-in"  data-in="${{n.id}}"></div>` : ''}}
         ${{cfg.out ? `<div class="port port-out" data-out="${{n.id}}"></div>` : ''}}
       </div>`;
    canvas.appendChild(el);
  }});
}}

function renderEdges() {{
  const svg = document.getElementById('svg-layer');
  svg.innerHTML = '';
  edges.forEach((e, i) => {{
    if (!nodes[e.from] || !nodes[e.to]) return;
    const p1=outPt(e.from), p2=inPt(e.to);
    const path = makePath(bezier(p1.x,p1.y,p2.x,p2.y), '#6366f1', false);
    path.addEventListener('click', () => {{ edges.splice(i,1); render(); }});
    svg.appendChild(path);
  }});
  auxEdges.forEach(e => {{
    if (!nodes[e.from] || !nodes[e.to]) return;
    const p1=outPt(e.from), p2=inPt(e.to);
    const path = makePath(bezier(p1.x,p1.y,p2.x,p2.y), edgeColor(e.connType), true);
    path.setAttribute('opacity', '0.9');
    path.setAttribute('title', e.connType);
    svg.appendChild(path);
  }});
  if (conn) {{
    const p1 = outPt(conn.fromId);
    svg.appendChild(makePath(bezier(p1.x,p1.y,conn.mx,conn.my), '#94a3b8', true));
  }}
}}

function makePath(d, stroke, dashed) {{
  const p = document.createElementNS('http://www.w3.org/2000/svg','path');
  p.setAttribute('d', d);
  p.setAttribute('stroke', stroke);
  p.setAttribute('stroke-width', '2.5');
  p.setAttribute('fill', 'none');
  p.setAttribute('stroke-linecap', 'round');
  if (dashed) p.setAttribute('stroke-dasharray', '6 4');
  return p;
}}

function edgeColor(connType) {{
  if (connType === 'ai_languageModel') return '#f59e0b';
  if (connType === 'ai_memory') return '#14b8a6';
  if (connType === 'ai_tool') return '#ec4899';
  if (connType === 'ai_outputParser') return '#8b5cf6';
  return '#64748b';
}}

// ── Mutations ────────────────────────────────────────────────────────────────
function addNode(type) {{
  const id = 'n'+(nxtId++);
  const cfg = NODE_TYPES[type];
  nodes[id] = {{id, name:cfg.label, type, x:180+Math.random()*400, y:80+Math.random()*300, parameters:{{}}}};
  render();
}}

function deleteNode(id) {{
  delete nodes[id];
  edges = edges.filter(e => e.from!==id && e.to!==id);
  auxEdges = auxEdges.filter(e => e.from!==id && e.to!==id);
  render();
}}

// ── Events ───────────────────────────────────────────────────────────────────
function setupEvents() {{
  const wrap = document.getElementById('canvas-wrap');

  wrap.addEventListener('mousedown', e => {{
    const dragEl = e.target.closest('[data-drag]');
    if (dragEl) {{
      const nid = dragEl.dataset.drag;
      drag = {{nodeId:nid, mx0:e.clientX, my0:e.clientY, nx0:nodes[nid].x, ny0:nodes[nid].y}};
      e.preventDefault(); return;
    }}
    const outEl = e.target.closest('[data-out]');
    if (outEl) {{
      const wRect = wrap.getBoundingClientRect();
      const pRect = outEl.getBoundingClientRect();
      conn = {{fromId:outEl.dataset.out,
               mx: pRect.left-wRect.left+wrap.scrollLeft+6,
               my: pRect.top -wRect.top +wrap.scrollTop +6}};
      e.preventDefault(); return;
    }}
    const delEl = e.target.closest('[data-del]');
    if (delEl) {{ deleteNode(delEl.dataset.del); }}
  }});

  wrap.addEventListener('mousemove', e => {{
    if (!drag && !conn) return;
    const wRect = wrap.getBoundingClientRect();
    if (drag) {{
      nodes[drag.nodeId].x = Math.max(0, drag.nx0 + e.clientX - drag.mx0);
      nodes[drag.nodeId].y = Math.max(0, drag.ny0 + e.clientY - drag.my0);
      const el = document.getElementById('node-'+drag.nodeId);
      if (el) {{ el.style.left=nodes[drag.nodeId].x+'px'; el.style.top=nodes[drag.nodeId].y+'px'; }}
      renderEdges();
    }}
    if (conn) {{
      conn.mx = e.clientX - wRect.left + wrap.scrollLeft;
      conn.my = e.clientY - wRect.top  + wrap.scrollTop;
      renderEdges();
    }}
  }});

  document.addEventListener('mouseup', e => {{
    if (conn) {{
      const inEl = e.target.closest('[data-in]');
      if (inEl) {{
        const tid = inEl.dataset.in;
        if (tid !== conn.fromId && !edges.find(ed=>ed.from===conn.fromId&&ed.to===tid))
          edges.push({{from:conn.fromId, to:tid}});
      }}
      conn = null; render();
    }}
    drag = null;
  }});

  document.getElementById('run-btn').addEventListener('click', runWorkflow);
  document.getElementById('copy-btn').addEventListener('click', () => {{
    const json = JSON.stringify(buildWorkflow(), null, 2);
    if (navigator.clipboard) {{
      navigator.clipboard.writeText(json).then(() => alert('Copied to clipboard!'));
    }} else {{
      prompt('Workflow JSON:', json);
    }}
  }});
}}

// ── Serialization ─────────────────────────────────────────────────────────────
function buildWorkflow() {{
  const nodeList = Object.values(nodes).map(n => ({{
    id:n.id, name:n.name, type:n.type, typeVersion:1,
    position:[Math.round(n.x-60), Math.round(n.y-60)],
    parameters:n.parameters,
  }}));
  const conns = {{}};
  edges.forEach(e => {{
    const fn=nodes[e.from], tn=nodes[e.to]; if (!fn||!tn) return;
    if (!conns[fn.name]) conns[fn.name] = {{main:[[]]}};
    conns[fn.name].main[0].push({{node:tn.name,type:'main',index:0}});
  }});
  auxEdges.forEach(e => {{
    const fn=nodes[e.from], tn=nodes[e.to]; if (!fn||!tn||!e.connType) return;
    if (!conns[fn.name]) conns[fn.name] = {{}};
    if (!conns[fn.name][e.connType]) conns[fn.name][e.connType] = [[]];
    conns[fn.name][e.connType][0].push({{node:tn.name,type:e.connType,index:0}});
  }});
  return {{...WORKFLOW, nodes:nodeList, connections:conns}};
}}

// ── Execution ─────────────────────────────────────────────────────────────────
async function runWorkflow() {{
  const btn = document.getElementById('run-btn');
  const panel = document.getElementById('output-panel');
  const content = document.getElementById('output-content');
  btn.disabled = true; btn.textContent = '&#9203; Running...';
  panel.style.display = 'flex'; content.textContent = '';

  try {{
    const resp = await fetch(BACKEND_URL + '/run_workflow', {{
      method:'POST', headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{
        workflow: buildWorkflow(),
        session_id: 'editor-' + Date.now(),
        chat_history: [],
      }}),
    }});
    if (!resp.ok) {{ content.textContent = 'Error: HTTP ' + resp.status; return; }}

    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    while (true) {{
      const {{done, value}} = await reader.read(); if (done) break;
      buf += dec.decode(value, {{stream:true}});
      const lines = buf.split('\\n'); buf = lines.pop();
      lines.forEach(line => {{
        if (!line.trim()) return;
        try {{
          const ev = JSON.parse(line);
          const txt = ev.text || ev.message || '';
          if (txt) content.textContent += txt + '\\n\\n';
        }} catch {{ content.textContent += line + '\\n'; }}
        panel.scrollTop = panel.scrollHeight;
      }});
    }}
  }} catch(err) {{
    content.textContent = 'Error: ' + err.message;
  }} finally {{
    btn.disabled = false; btn.textContent = '&#9654; Run';
  }}
}}

function closeOutput() {{
  document.getElementById('output-panel').style.display = 'none';
}}

init();
</script>
</body>
</html>"""

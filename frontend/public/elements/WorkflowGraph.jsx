const TYPE_STYLES = {
  agent: {
    background: "#e0f2fe",
    color: "#0c4a6e",
    border: "#7dd3fc",
  },
  api: {
    background: "#dcfce7",
    color: "#166534",
    border: "#86efac",
  },
  rag: {
    background: "#fef3c7",
    color: "#92400e",
    border: "#fcd34d",
  },
};

function badgeStyle(type) {
  const palette = TYPE_STYLES[type] || {
    background: "#f3f4f6",
    color: "#374151",
    border: "#d1d5db",
  };

  return {
    display: "inline-flex",
    alignItems: "center",
    padding: "2px 8px",
    borderRadius: "999px",
    fontSize: 12,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.04em",
    background: palette.background,
    color: palette.color,
    border: `1px solid ${palette.border}`,
  };
}

function cardStyle({ isLast, isActive, isCompleted }) {
  let border = "1px solid #e5e7eb";
  let background = "#ffffff";
  let boxShadow = "0 8px 24px rgba(15, 23, 42, 0.06)";

  if (isCompleted) {
    border = "1px solid #86efac";
    background = "#f0fdf4";
    boxShadow = "0 8px 24px rgba(34, 197, 94, 0.12)";
  }

  if (isActive) {
    border = "1px solid #38bdf8";
    background = "linear-gradient(135deg, #eff6ff 0%, #ecfeff 100%)";
    boxShadow = "0 0 0 4px rgba(56, 189, 248, 0.18), 0 12px 28px rgba(14, 165, 233, 0.18)";
  }

  return {
    border,
    borderRadius: 14,
    padding: 14,
    background,
    boxShadow,
    marginBottom: isLast ? 0 : 12,
    transition: "all 180ms ease",
  };
}

function statusText(isActive, isCompleted) {
  if (isActive) return "Running now";
  if (isCompleted) return "Completed";
  return "Pending";
}

function WorkflowNodeCard({ node, nextNodes, isLast, isActive, isCompleted }) {
  return (
    <div style={cardStyle({ isLast, isActive, isCompleted })}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 12,
          marginBottom: 10,
        }}
      >
        <div style={{ fontSize: 16, fontWeight: 700, color: "#111827" }}>{node.name}</div>
        <span style={badgeStyle(node.type)}>{node.type}</span>
      </div>

      <div
        style={{
          fontSize: 13,
          fontWeight: 700,
          color: isActive ? "#0369a1" : isCompleted ? "#15803d" : "#6b7280",
          marginBottom: 8,
        }}
      >
        {statusText(isActive, isCompleted)}
      </div>

      <div style={{ fontSize: 13, color: "#6b7280", marginBottom: 6 }}>Next step</div>
      <div style={{ fontSize: 14, color: "#1f2937", lineHeight: 1.5 }}>
        {nextNodes.length > 0 ? nextNodes.join(", ") : "Final node"}
      </div>
    </div>
  );
}

export default function WorkflowGraph() {
  const scopeProps = typeof props === "object" && props !== null ? props : {};
  const workflow = scopeProps.workflow || {};
  const activeNode = scopeProps.active_node || null;
  const completedNodes = Array.isArray(scopeProps.completed_nodes) ? scopeProps.completed_nodes : [];
  const nodes = Array.isArray(workflow.nodes) ? workflow.nodes : [];
  const connections = workflow.connections || {};
  const branchCount = Object.values(connections).filter(
    (targets) => Array.isArray(targets) && targets.length > 1
  ).length;

  return (
    <div
      style={{
        fontFamily:
          'ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        background: "linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%)",
        minHeight: "100%",
        padding: 16,
      }}
    >
      <div
        style={{
          marginBottom: 16,
          padding: 16,
          borderRadius: 16,
          background: "#0f172a",
          color: "#f8fafc",
        }}
      >
        <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: "0.08em", opacity: 0.72 }}>
          WORKFLOW
        </div>
        <div style={{ fontSize: 22, fontWeight: 800, marginTop: 4 }}>{nodes.length} nodes</div>
        <div style={{ fontSize: 14, opacity: 0.8, marginTop: 8 }}>
          Live execution plan for the current request
        </div>
        <div style={{ fontSize: 13, opacity: 0.72, marginTop: 10 }}>
          {branchCount > 0 ? `${branchCount} adaptive branch point` : "Linear plan"}
          {activeNode ? ` • Active: ${activeNode}` : ""}
        </div>
      </div>

      {nodes.length === 0 ? (
        <div
          style={{
            borderRadius: 14,
            border: "1px dashed #cbd5e1",
            background: "rgba(255, 255, 255, 0.82)",
            padding: 20,
            color: "#475569",
            fontSize: 14,
          }}
        >
          No workflow nodes were provided.
        </div>
      ) : (
        nodes.map((node, index) => (
          <WorkflowNodeCard
            key={node.name || index}
            node={node}
            nextNodes={Array.isArray(connections[node.name]) ? connections[node.name] : []}
            isLast={index === nodes.length - 1}
            isActive={activeNode === node.name}
            isCompleted={completedNodes.includes(node.name)}
          />
        ))
      )}
    </div>
  );
}

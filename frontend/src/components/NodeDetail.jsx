// Format ISO dates to DD-MM-YYYY, time objects to HH:MM:SS
function formatValue(value) {
  if (value == null) return "—";

  // Time object like {hours:5, minutes:2, seconds:26}
  if (typeof value === "object" && value !== null && "hours" in value) {
    const h = String(value.hours ?? 0).padStart(2, "0");
    const m = String(value.minutes ?? 0).padStart(2, "0");
    const s = String(value.seconds ?? 0).padStart(2, "0");
    return `${h}:${m}:${s}`;
  }

  if (typeof value === "object") return JSON.stringify(value);

  const str = String(value);

  // ISO date: 2025-04-02 or 2025-04-02T... → 02-04-2025
  const dateMatch = str.match(/^(\d{4})-(\d{2})-(\d{2})(T|$)/);
  if (dateMatch) {
    return `${dateMatch[3]}-${dateMatch[2]}-${dateMatch[1]}`;
  }

  return str;
}

export default function NodeDetail({ node, connectionCount, onClose }) {
  if (!node) return null;

  return (
    <div className="node-card">
      <button className="node-card-close" onClick={onClose}>&times;</button>

      <div className="node-card-header" style={{ borderColor: node.color }}>
        <span className="node-color-dot" style={{ background: node.color }} />
        <span className="node-card-type">{node.type.replace(/_/g, " ")}</span>
      </div>

      <div className="node-card-body">
        {Object.entries(node.data || {}).map(([key, value]) => (
          <div className="node-card-row" key={key}>
            <span className="node-card-key">{key}</span>
            <span className="node-card-value">{formatValue(value)}</span>
          </div>
        ))}
      </div>

      <div className="node-card-footer">
        <span className="node-card-connections">
          {connectionCount} connection{connectionCount !== 1 ? "s" : ""}
        </span>
      </div>
    </div>
  );
}

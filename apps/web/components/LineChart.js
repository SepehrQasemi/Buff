export default function LineChart({ data, height = 160 }) {
  const points = Array.isArray(data) ? data.filter((item) => Number.isFinite(item.y)) : [];
  if (points.length < 2) {
    return (
      <div className="card soft" style={{ height }}>
        <p style={{ margin: 0, color: "var(--muted)" }}>Not enough data to chart.</p>
      </div>
    );
  }

  const values = points.map((item) => item.y);
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) {
    min -= 1;
    max += 1;
  }

  const viewPoints = points
    .map((item, index) => {
      const x = (index / (points.length - 1)) * 100;
      const y = 100 - ((item.y - min) / (max - min)) * 100;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <div className="card soft" style={{ padding: "12px" }}>
      <svg
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        style={{ width: "100%", height }}
      >
        <defs>
          <linearGradient id="lineFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="rgba(15, 107, 95, 0.35)" />
            <stop offset="100%" stopColor="rgba(15, 107, 95, 0.05)" />
          </linearGradient>
        </defs>
        <polyline
          fill="none"
          stroke="var(--accent)"
          strokeWidth="1.5"
          points={viewPoints}
        />
        <polygon fill="url(#lineFill)" points={`0,100 ${viewPoints} 100,100`} />
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem" }}>
        <span style={{ color: "var(--muted)" }}>{min.toFixed(2)}</span>
        <span style={{ color: "var(--muted)" }}>{max.toFixed(2)}</span>
      </div>
    </div>
  );
}

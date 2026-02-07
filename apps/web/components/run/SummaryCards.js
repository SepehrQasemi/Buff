const normalizeSamples = (summary) => {
  const detail = Array.isArray(summary?.malformed_samples_detail)
    ? summary.malformed_samples_detail
    : [];
  const fallback = Array.isArray(summary?.malformed_samples) ? summary.malformed_samples : [];

  if (detail.length) {
    return detail.map((item, index) => ({
      line_number: item.line_number ?? index + 1,
      error: item.error || "Invalid JSON",
      raw_preview: item.raw_preview || item.raw || "",
    }));
  }

  return fallback.map((raw, index) => ({
    line_number: index + 1,
    error: "Invalid JSON",
    raw_preview: raw || "",
  }));
};

const truncate = (value, limit = 240) => {
  if (!value) {
    return "";
  }
  if (value.length <= limit) {
    return value;
  }
  return `${value.slice(0, limit)}…`;
};

export default function SummaryCards({ summary, loading, error }) {
  if (error) {
    return <div className="banner">{error}</div>;
  }

  if (loading) {
    return <div className="card">Loading summary...</div>;
  }

  if (!summary) {
    return null;
  }

  const malformedCount = summary.malformed_lines_count || 0;
  const samples = normalizeSamples(summary);

  return (
    <section className="card" style={{ marginBottom: "24px" }}>
      <div className="section-title">
        <h2>Summary</h2>
        <p>Malformed lines: {malformedCount}</p>
      </div>
      <div className="grid three" style={{ marginBottom: "16px" }}>
        <div className="kpi">
          <span>Min timestamp</span>
          <strong>{summary.min_timestamp || "n/a"}</strong>
        </div>
        <div className="kpi">
          <span>Max timestamp</span>
          <strong>{summary.max_timestamp || "n/a"}</strong>
        </div>
        <div className="kpi">
          <span>Actions</span>
          <strong>{Object.keys(summary.counts_by_action || {}).length}</strong>
        </div>
        <div className="kpi">
          <span>Severities</span>
          <strong>{Object.keys(summary.counts_by_severity || {}).length}</strong>
        </div>
        <div className="kpi">
          <span>Malformed lines</span>
          <strong>{malformedCount}</strong>
        </div>
      </div>
      {malformedCount > 0 && samples.length > 0 && (
        <details className="malformed-panel">
          <summary>Show malformed JSONL samples</summary>
          <div className="malformed-list">
            {samples.map((sample, index) => (
              <div key={`${sample.line_number}-${index}`} className="malformed-sample">
                <div className="malformed-meta">
                  <strong>Line {sample.line_number}</strong>
                  <span>{sample.error}</span>
                </div>
                <pre>{truncate(sample.raw_preview)}</pre>
              </div>
            ))}
          </div>
        </details>
      )}
    </section>
  );
}

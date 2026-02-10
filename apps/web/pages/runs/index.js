import Link from "next/link";
import { useEffect, useState } from "react";
import { getRuns } from "../../lib/api";

const formatError = (result, fallback) => {
  if (!result) {
    return fallback;
  }
  if (!result.status) {
    return `${fallback}: ${result.error || "API unreachable"}`;
  }
  return `${result.error || fallback} (HTTP ${result.status})`;
};

export default function RunsPage() {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    async function load() {
      const result = await getRuns();
      if (!active) {
        return;
      }
      if (!result.ok) {
        setError(formatError(result, "Failed to load runs"));
        setLoading(false);
        return;
      }
      setRuns(Array.isArray(result.data) ? result.data : []);
      setLoading(false);
    }
    load();
    return () => {
      active = false;
    };
  }, []);

  return (
    <main>
      <header>
        <div className="header-title">
          <h1>Runs</h1>
          <span>Open a run in the chart workspace (read-only).</span>
        </div>
        <span className="badge info">{runs.length} runs</span>
      </header>

      {error && <div className="banner">{error}</div>}

      {loading ? (
        <div className="card fade-up">Loading runs...</div>
      ) : runs.length === 0 ? (
        <div className="card fade-up">No runs found under artifacts.</div>
      ) : (
        <div className="grid two">
          {runs.map((run, index) => (
            <Link
              key={run.id}
              href={`/runs/${run.id}`}
              className="card fade-up"
              style={{ animationDelay: `${index * 60}ms` }}
            >
              <div className="section-title">
                <h3>{run.id}</h3>
                <span className={`badge ${run.status === "OK" ? "ok" : "invalid"}`}>
                  {run.status}
                </span>
              </div>
              <p style={{ margin: "4px 0", color: "var(--muted)" }}>{run.path}</p>
              <div className="grid two" style={{ marginTop: "12px" }}>
                <div className="kpi">
                  <span>Created</span>
                  <strong>{run.created_at || "n/a"}</strong>
                </div>
                <div className="kpi">
                  <span>Strategy</span>
                  <strong>{run.strategy || "n/a"}</strong>
                </div>
                <div className="kpi">
                  <span>Symbols</span>
                  <strong>{Array.isArray(run.symbols) ? run.symbols.join(", ") : "n/a"}</strong>
                </div>
                <div className="kpi">
                  <span>Timeframe</span>
                  <strong>{run.timeframe || "n/a"}</strong>
                </div>
              </div>
              {run.has_trades && (
                <span className="badge info" style={{ marginTop: "12px" }}>
                  Trades ready
                </span>
              )}
              <span className="badge ok" style={{ marginTop: "8px" }}>
                Open Workspace
              </span>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}

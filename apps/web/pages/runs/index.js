import Link from "next/link";
import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export default function RunsPage() {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const response = await fetch(`${API_BASE}/api/runs`);
        if (!response.ok) {
          throw new Error(`Failed to load runs (${response.status})`);
        }
        const data = await response.json();
        if (active) {
          setRuns(Array.isArray(data) ? data : []);
        }
      } catch (err) {
        if (active) {
          setError(err.message || "Failed to load runs");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
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
          <span>Latest Buff runs discovered from artifacts.</span>
        </div>
        <span className="badge info">{runs.length} runs</span>
      </header>

      {error && (
        <div className="banner">
          {error} — check that the API is running on {API_BASE}.
        </div>
      )}

      {loading ? (
        <div className="card fade-up">Loading runs...</div>
      ) : runs.length === 0 ? (
        <div className="card fade-up">No runs found under artifacts.</div>
      ) : (
        <div className="grid two">
          {runs.map((run, index) => (
            <Link key={run.id} href={`/runs/${run.id}`} className="card fade-up" style={{ animationDelay: `${index * 60}ms` }}>
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
              {run.has_trades && <span className="badge info" style={{ marginTop: "12px" }}>Trades ready</span>}
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}

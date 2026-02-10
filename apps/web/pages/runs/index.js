import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useMemo, useState } from "react";
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
  const router = useRouter();
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedRuns, setSelectedRuns] = useState([]);

  const compareEnabled = selectedRuns.length === 2;
  const compareHref = useMemo(() => {
    if (!compareEnabled) {
      return "";
    }
    const [runA, runB] = selectedRuns;
    return `/runs/compare?runA=${encodeURIComponent(runA)}&runB=${encodeURIComponent(
      runB
    )}`;
  }, [compareEnabled, selectedRuns]);

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

  useEffect(() => {
    setSelectedRuns((current) =>
      current.filter((id) => runs.some((run) => run.id === id))
    );
  }, [runs]);

  const toggleSelection = (runId) => {
    setSelectedRuns((current) => {
      if (current.includes(runId)) {
        return current.filter((id) => id !== runId);
      }
      const next = [...current, runId];
      if (next.length > 2) {
        next.shift();
      }
      return next;
    });
  };

  const handleSelectionClick = (event, runId) => {
    event.preventDefault();
    event.stopPropagation();
    toggleSelection(runId);
  };

  const handleCompare = () => {
    if (!compareEnabled) {
      return;
    }
    router.push(compareHref);
  };

  return (
    <main>
      <header>
        <div className="header-title">
          <h1>Runs</h1>
          <span>Open a run in the chart workspace (read-only).</span>
        </div>
        <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
          <span className="badge info">{runs.length} runs</span>
          <span className="badge">{selectedRuns.length} selected</span>
          <button className="secondary" disabled={!compareEnabled} onClick={handleCompare}>
            Compare
          </button>
        </div>
      </header>

      {error && <div className="banner">{error}</div>}

      {loading ? (
        <div className="card fade-up">Loading runs...</div>
      ) : runs.length === 0 ? (
        <div className="card fade-up">No runs found under artifacts.</div>
      ) : (
        <div className="grid two">
          {runs.map((run, index) => {
            const selected = selectedRuns.includes(run.id);
            return (
              <Link
                key={run.id}
                href={`/runs/${run.id}`}
                className="card fade-up"
                style={{ animationDelay: `${index * 60}ms` }}
              >
                <div className="section-title">
                  <h3>{run.id}</h3>
                  <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                    <span className={`badge ${run.status === "OK" ? "ok" : "invalid"}`}>
                      {run.status}
                    </span>
                    <label
                      className="muted"
                      style={{ display: "flex", gap: "6px", alignItems: "center" }}
                      onClick={(event) => handleSelectionClick(event, run.id)}
                    >
                      <input
                        type="checkbox"
                        checked={selected}
                        readOnly
                      />
                      Compare
                    </label>
                  </div>
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
                    <strong>
                      {Array.isArray(run.symbols) ? run.symbols.join(", ") : "n/a"}
                    </strong>
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
            );
          })}
        </div>
      )}
    </main>
  );
}

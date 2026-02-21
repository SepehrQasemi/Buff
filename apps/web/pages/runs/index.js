import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useMemo, useState } from "react";
import AppShell from "../../components/AppShell";
import ErrorNotice from "../../components/ErrorNotice";
import { getDataImports, getObservabilityRuns } from "../../lib/api";
import { mapApiErrorDetails } from "../../lib/errorMapping";

const normalizeRun = (row) => {
  if (!row || typeof row !== "object") {
    return null;
  }
  const runId = row.run_id || row.id;
  if (!runId) {
    return null;
  }
  return {
    run_id: String(runId),
    state: row.state || row.status || "UNKNOWN",
    strategy_id: row.strategy_id || row.strategy || null,
    risk_level: Number.isInteger(row.risk_level) ? row.risk_level : null,
    created_at: row.created_at || null,
    updated_at: row.updated_at || row.last_verified_at || null,
    artifact_status: row.artifact_status || null,
    validation_status: row.validation_status || null,
    error_code: row.error_code || null,
  };
};

const statusBadge = (state) => {
  const text = String(state || "UNKNOWN").toUpperCase();
  if (text === "CORRUPTED" || text === "FAILED") {
    return { text, kind: "invalid" };
  }
  if (text === "COMPLETED" || text === "OK") {
    return { text, kind: "ok" };
  }
  return { text, kind: "info" };
};

export default function RunsPage() {
  const router = useRouter();
  const [runs, setRuns] = useState([]);
  const [datasetCount, setDatasetCount] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [selectedRuns, setSelectedRuns] = useState([]);
  const [stateFilter, setStateFilter] = useState("ALL");
  const [strategyFilter, setStrategyFilter] = useState("ALL");
  const [riskFilter, setRiskFilter] = useState("ALL");

  useEffect(() => {
    let active = true;
    async function load() {
      const [runsResult, importsResult] = await Promise.all([
        getObservabilityRuns({ cache: true, bypassCache: true }),
        getDataImports(),
      ]);
      if (!active) {
        return;
      }
      if (!runsResult.ok) {
        setError(mapApiErrorDetails(runsResult, "Failed to load run observability index"));
        setRuns([]);
        setLoading(false);
        return;
      }
      const payloadRuns = Array.isArray(runsResult.data?.runs) ? runsResult.data.runs : [];
      const normalized = payloadRuns.map(normalizeRun).filter(Boolean);
      setRuns(normalized);
      if (importsResult.ok) {
        setDatasetCount(Number.isFinite(importsResult.data?.total) ? importsResult.data.total : 0);
      } else {
        setDatasetCount(null);
      }
      setError(null);
      setLoading(false);
    }
    setLoading(true);
    load();
    return () => {
      active = false;
    };
  }, [reloadToken]);

  useEffect(() => {
    setSelectedRuns((current) => current.filter((id) => runs.some((run) => run.run_id === id)));
  }, [runs]);

  const stateOptions = useMemo(() => {
    const values = new Set();
    runs.forEach((run) => values.add(String(run.state || "UNKNOWN")));
    return ["ALL", ...Array.from(values).sort()];
  }, [runs]);

  const strategyOptions = useMemo(() => {
    const values = new Set();
    runs.forEach((run) => {
      if (run.strategy_id) {
        values.add(String(run.strategy_id));
      }
    });
    return ["ALL", ...Array.from(values).sort()];
  }, [runs]);

  const riskOptions = useMemo(() => {
    const values = new Set();
    runs.forEach((run) => {
      if (Number.isInteger(run.risk_level)) {
        values.add(String(run.risk_level));
      }
    });
    return ["ALL", ...Array.from(values).sort((a, b) => Number(a) - Number(b))];
  }, [runs]);

  const filteredRuns = useMemo(() => {
    return runs.filter((run) => {
      if (stateFilter !== "ALL" && String(run.state) !== stateFilter) {
        return false;
      }
      if (strategyFilter !== "ALL" && String(run.strategy_id || "") !== strategyFilter) {
        return false;
      }
      if (riskFilter !== "ALL" && String(run.risk_level ?? "") !== riskFilter) {
        return false;
      }
      return true;
    });
  }, [runs, stateFilter, strategyFilter, riskFilter]);

  const compareEnabled = selectedRuns.length === 2;
  const compareHref = useMemo(() => {
    if (!compareEnabled) {
      return "";
    }
    const [runA, runB] = selectedRuns;
    return `/runs/compare?runA=${encodeURIComponent(runA)}&runB=${encodeURIComponent(runB)}`;
  }, [compareEnabled, selectedRuns]);

  const toggleSelection = (event, runId) => {
    event.preventDefault();
    event.stopPropagation();
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

  const retryLoad = () => {
    setReloadToken((value) => value + 1);
  };

  return (
    <AppShell>
      <main>
        <header>
          <div className="header-title">
            <h1>Run Explorer</h1>
            <span>Artifact-backed run lifecycle and observability view.</span>
          </div>
          <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
            <span className="badge info">{filteredRuns.length} visible</span>
            <span className="badge">{selectedRuns.length} selected</span>
            <button
              className="secondary"
              disabled={!compareEnabled}
              onClick={() => compareEnabled && router.push(compareHref)}
            >
              Compare
            </button>
          </div>
        </header>

        {error && <ErrorNotice error={error} onRetry={retryLoad} />}

        <section className="card fade-up" style={{ marginBottom: "16px" }}>
          <div className="section-title">
            <h3>Filters</h3>
            <button className="secondary" onClick={retryLoad}>
              Refresh
            </button>
          </div>
          <div className="grid three">
            <label>
              State
              <select value={stateFilter} onChange={(event) => setStateFilter(event.target.value)}>
                {stateOptions.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Strategy
              <select
                value={strategyFilter}
                onChange={(event) => setStrategyFilter(event.target.value)}
              >
                {strategyOptions.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Risk Level
              <select value={riskFilter} onChange={(event) => setRiskFilter(event.target.value)}>
                {riskOptions.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </section>

        {loading ? (
          <div className="card fade-up">Loading runs...</div>
        ) : runs.length === 0 ? (
          <div className="card fade-up">
            <h3 style={{ marginBottom: "8px" }}>Create Your First Run</h3>
            <p className="muted" style={{ marginTop: 0 }}>
              No runs found yet. Start by importing data and creating a run.
            </p>
            <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
              <button onClick={() => router.push("/runs/new")}>Create Your First Run</button>
              {datasetCount === 0 && (
                <button className="secondary" onClick={() => router.push("/runs/new")}>
                  Import Data
                </button>
              )}
            </div>
          </div>
        ) : filteredRuns.length === 0 ? (
          <div className="card fade-up">No runs match the selected filters.</div>
        ) : (
          <div className="grid two">
            {filteredRuns.map((run, index) => {
              const selected = selectedRuns.includes(run.run_id);
              const badge = statusBadge(run.state);
              return (
                <Link
                  key={run.run_id}
                  href={`/runs/${run.run_id}`}
                  className="card fade-up"
                  style={{ animationDelay: `${index * 40}ms` }}
                >
                  <div className="section-title">
                    <h3>{run.run_id}</h3>
                    <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                      <span className={`badge ${badge.kind}`}>{badge.text}</span>
                      {run.artifact_status && (
                        <span className="badge info">{run.artifact_status}</span>
                      )}
                      <label
                        className="muted"
                        style={{ display: "flex", gap: "6px", alignItems: "center" }}
                        onClick={(event) => toggleSelection(event, run.run_id)}
                      >
                        <input type="checkbox" checked={selected} readOnly />
                        Compare
                      </label>
                    </div>
                  </div>
                  <div className="grid two" style={{ marginTop: "12px" }}>
                    <div className="kpi">
                      <span>Strategy</span>
                      <strong>{run.strategy_id || "n/a"}</strong>
                    </div>
                    <div className="kpi">
                      <span>Risk Level</span>
                      <strong>{run.risk_level ?? "n/a"}</strong>
                    </div>
                    <div className="kpi">
                      <span>Created</span>
                      <strong>{run.created_at || "n/a"}</strong>
                    </div>
                    <div className="kpi">
                      <span>Updated</span>
                      <strong>{run.updated_at || "n/a"}</strong>
                    </div>
                  </div>
                  <div style={{ marginTop: "12px", display: "flex", gap: "8px", flexWrap: "wrap" }}>
                    <span className={`badge ${run.validation_status === "pass" ? "ok" : "invalid"}`}>
                      Validation {run.validation_status || "unknown"}
                    </span>
                    {run.error_code && <span className="badge invalid">{run.error_code}</span>}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </main>
    </AppShell>
  );
}

import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useMemo, useState } from "react";
import AppShell from "../../components/AppShell";
import CandlestickChart from "../../components/workspace/CandlestickChart";
import ErrorNotice from "../../components/ErrorNotice";
import { getExperimentComparison, getExperimentManifest } from "../../lib/api";
import { buildClientError, mapApiErrorDetails, mapErrorPayload } from "../../lib/errorMapping";
import useWorkspace from "../../lib/useWorkspace";

const TABS = [
  { id: "tester", label: "Tester" },
  { id: "failures", label: "Failures" },
  { id: "manifest", label: "Manifest" },
];

const statusBadgeKind = (status) => {
  const normalized = String(status || "").toUpperCase();
  if (normalized === "COMPLETED" || normalized === "OK") {
    return "ok";
  }
  if (normalized === "PARTIAL") {
    return "info";
  }
  return "invalid";
};

const toText = (value, fallback = "n/a") => {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }
  return String(value);
};

const normalizeExperimentId = (rawValue) => {
  if (Array.isArray(rawValue)) {
    return String(rawValue[0] || "").trim();
  }
  return String(rawValue || "").trim();
};

const compareValues = (left, right) => {
  if (left === right) {
    return 0;
  }
  const leftNumber = Number(left);
  const rightNumber = Number(right);
  const bothNumbers = Number.isFinite(leftNumber) && Number.isFinite(rightNumber);
  if (bothNumbers) {
    return leftNumber - rightNumber;
  }
  return String(left ?? "").localeCompare(String(right ?? ""));
};

export default function ExperimentDetailPage() {
  const router = useRouter();
  const experimentId = normalizeExperimentId(router.query.experiment_id);
  const isReady = router.isReady;

  const [activeTab, setActiveTab] = useState("tester");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [manifest, setManifest] = useState(null);
  const [comparison, setComparison] = useState(null);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [sortConfig, setSortConfig] = useState({
    column: "candidate_index",
    direction: "asc",
  });
  const [manifestCopied, setManifestCopied] = useState(false);

  useEffect(() => {
    setManifestCopied(false);
  }, [experimentId]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      if (!isReady) {
        return;
      }
      if (!experimentId) {
        setError(
          buildClientError({
            title: "Missing experiment id",
            summary: "Open /experiments/<experiment_id> with a valid id.",
          })
        );
        setManifest(null);
        setComparison(null);
        return;
      }
      setLoading(true);
      setError(null);
      const [manifestResult, comparisonResult] = await Promise.all([
        getExperimentManifest(experimentId),
        getExperimentComparison(experimentId),
      ]);
      if (!active) {
        return;
      }
      if (!manifestResult.ok) {
        setManifest(null);
        setComparison(null);
        setError(mapApiErrorDetails(manifestResult, "Failed to load experiment manifest"));
        setLoading(false);
        return;
      }
      if (!comparisonResult.ok) {
        setManifest(null);
        setComparison(null);
        setError(mapApiErrorDetails(comparisonResult, "Failed to load comparison summary"));
        setLoading(false);
        return;
      }
      setManifest(manifestResult.data);
      setComparison(comparisonResult.data);
      setLoading(false);
    };
    load();
    return () => {
      active = false;
    };
  }, [experimentId, isReady]);

  const manifestCandidates = useMemo(
    () => (Array.isArray(manifest?.candidates) ? manifest.candidates : []),
    [manifest]
  );
  const comparisonRows = useMemo(
    () => (Array.isArray(comparison?.rows) ? comparison.rows : []),
    [comparison]
  );
  const comparisonColumns = useMemo(
    () => (Array.isArray(comparison?.columns) ? comparison.columns : []),
    [comparison]
  );

  const successfulCandidates = useMemo(() => {
    const rowsByCandidateId = new Map(
      comparisonRows
        .map((row) => [String(row?.candidate_id || ""), row])
        .filter(([candidateId]) => candidateId)
    );
    return manifestCandidates
      .filter((candidate) => candidate && typeof candidate === "object")
      .map((candidate, index) => {
        const runId = String(candidate.run_id || "").trim();
        if (!runId) {
          return null;
        }
        const candidateId = String(candidate.candidate_id || `cand_${String(index + 1).padStart(3, "0")}`);
        const row = rowsByCandidateId.get(candidateId) || null;
        const label = String(candidate.label || candidateId);
        const strategyId = row?.strategy_id ? String(row.strategy_id) : "";
        const runStatus = String(candidate.run_status || candidate.status || "").toUpperCase();
        return {
          candidateId,
          label,
          runId,
          runStatus,
          strategyId,
          displayLabel: strategyId ? `${label} (${strategyId})` : label,
        };
      })
      .filter(Boolean);
  }, [comparisonRows, manifestCandidates]);

  useEffect(() => {
    if (successfulCandidates.length === 0) {
      if (selectedRunId) {
        setSelectedRunId("");
      }
      return;
    }
    if (successfulCandidates.some((candidate) => candidate.runId === selectedRunId)) {
      return;
    }
    setSelectedRunId(successfulCandidates[0].runId);
  }, [selectedRunId, successfulCandidates]);

  const selectedCandidate = useMemo(
    () => successfulCandidates.find((candidate) => candidate.runId === selectedRunId) || null,
    [selectedRunId, successfulCandidates]
  );

  const lifecycleStateHint = selectedCandidate?.runStatus || "COMPLETED";
  const {
    run,
    runError,
    summaryError,
    ohlcv,
    ohlcvLoading,
    ohlcvError,
    markers,
    markersError,
    symbol,
    setSymbol,
    timeframe,
    setTimeframe,
    range,
    setRange,
    availableTimeframes,
    artifactsReady,
    reload,
  } = useWorkspace(selectedRunId, { lifecycleState: lifecycleStateHint });

  const [rangeDraft, setRangeDraft] = useState({ start_ts: "", end_ts: "" });

  useEffect(() => {
    setRangeDraft({
      start_ts: range?.start_ts || "",
      end_ts: range?.end_ts || "",
    });
  }, [range?.start_ts, range?.end_ts]);

  const applyRange = () => {
    setRange({
      start_ts: rangeDraft.start_ts,
      end_ts: rangeDraft.end_ts,
    });
  };

  const sortedRows = useMemo(() => {
    const rows = [...comparisonRows];
    const column = sortConfig?.column;
    if (!column) {
      return rows;
    }
    rows.sort((left, right) => compareValues(left?.[column], right?.[column]));
    if (sortConfig.direction === "desc") {
      rows.reverse();
    }
    return rows;
  }, [comparisonRows, sortConfig]);

  const failedCandidates = useMemo(
    () =>
      manifestCandidates.filter(
        (candidate) => String(candidate?.status || "").toUpperCase() === "FAILED"
      ),
    [manifestCandidates]
  );

  const overallStatus = String(manifest?.status || comparison?.status || "UNKNOWN").toUpperCase();
  const counts = comparison?.counts || manifest?.summary || {};
  const candles = Array.isArray(ohlcv?.candles) ? ohlcv.candles : [];
  const hasSuccessfulCandidates = successfulCandidates.length > 0;

  const toggleSort = (column) => {
    setSortConfig((current) => {
      if (current.column === column) {
        return {
          column,
          direction: current.direction === "asc" ? "desc" : "asc",
        };
      }
      return { column, direction: "asc" };
    });
  };

  const copyManifest = async () => {
    if (!manifest || typeof window === "undefined") {
      return;
    }
    const text = JSON.stringify(manifest, null, 2);
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        textarea.remove();
      }
      setManifestCopied(true);
      setTimeout(() => setManifestCopied(false), 1200);
    } catch {
      setManifestCopied(false);
    }
  };

  return (
    <AppShell fullBleed>
      <main className="workspace-shell" data-testid="experiment-workspace">
        <header className="workspace-header">
          <div>
            <div className="workspace-title">Experiment Workspace</div>
            <div className="workspace-subtitle">
              Experiment <strong>{experimentId || "..."}</strong> - chart-first artifact review
            </div>
          </div>
          <div className="workspace-actions">
            <span
              className={`badge ${statusBadgeKind(overallStatus)}`}
              data-testid="experiment-status"
            >
              {overallStatus}
            </span>
            {selectedRunId && (
              <Link href={`/runs/${selectedRunId}`}>
                <button type="button" className="secondary">
                  Open Selected Run
                </button>
              </Link>
            )}
            <Link href="/experiments">
              <button type="button" className="secondary">
                Back to Create
              </button>
            </Link>
          </div>
        </header>

        <section className="workspace-meta">
          <div className="meta-card">
            <div className="meta-label">Status</div>
            <div className="meta-value">{overallStatus}</div>
          </div>
          <div className="meta-card">
            <div className="meta-label">Total Candidates</div>
            <div className="meta-value">{toText(counts.total_candidates, "0")}</div>
          </div>
          <div className="meta-card">
            <div className="meta-label">Succeeded</div>
            <div className="meta-value">{toText(counts.succeeded, "0")}</div>
          </div>
          <div className="meta-card">
            <div className="meta-label">Failed</div>
            <div className="meta-value">{toText(counts.failed, "0")}</div>
          </div>
          <div className="meta-card">
            <div className="meta-label">Selected Baseline</div>
            <div className="meta-value">{selectedRunId || "none"}</div>
          </div>
        </section>

        {loading && (
          <section className="card fade-up" style={{ marginBottom: "16px" }}>
            <div className="section-title">
              <h3>Loading experiment artifacts...</h3>
            </div>
            <div style={{ display: "grid", gap: "10px" }}>
              <div style={{ height: "12px", borderRadius: "999px", background: "rgba(27,32,36,0.12)" }} />
              <div style={{ height: "12px", width: "84%", borderRadius: "999px", background: "rgba(27,32,36,0.1)" }} />
              <div style={{ height: "12px", width: "62%", borderRadius: "999px", background: "rgba(27,32,36,0.08)" }} />
            </div>
          </section>
        )}

        {error && <ErrorNotice error={error} mode="pro" onRetry={reload} />}

        {!loading && !error && (
          <div className="workspace-body">
            <section className="chart-panel">
              <div className="chart-toolbar">
                <label>
                  Baseline Run
                  <select
                    value={selectedRunId}
                    onChange={(event) => setSelectedRunId(event.target.value)}
                    disabled={!hasSuccessfulCandidates}
                  >
                    {!hasSuccessfulCandidates && <option value="">No successful runs</option>}
                    {successfulCandidates.map((candidate) => (
                      <option key={candidate.runId} value={candidate.runId}>
                        {candidate.displayLabel} - {candidate.runId}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  Symbol
                  <select
                    value={symbol}
                    onChange={(event) => setSymbol(event.target.value)}
                    disabled={!hasSuccessfulCandidates || !artifactsReady}
                  >
                    {(Array.isArray(run?.symbols) ? run.symbols : [symbol || ""])
                      .filter(Boolean)
                      .map((item) => (
                        <option key={item} value={item}>
                          {item}
                        </option>
                      ))}
                  </select>
                </label>

                <label>
                  Timeframe
                  <select
                    value={timeframe}
                    onChange={(event) => setTimeframe(event.target.value)}
                    disabled={!hasSuccessfulCandidates || !artifactsReady}
                  >
                    {(availableTimeframes.length ? availableTimeframes : [timeframe || "1m"]).map(
                      (item) => (
                        <option key={item} value={item}>
                          {item}
                        </option>
                      )
                    )}
                  </select>
                </label>

                <label>
                  Start (UTC)
                  <input
                    type="text"
                    value={rangeDraft.start_ts}
                    placeholder="2026-02-01T00:00:00Z"
                    onChange={(event) =>
                      setRangeDraft((current) => ({ ...current, start_ts: event.target.value }))
                    }
                    disabled={!hasSuccessfulCandidates || !artifactsReady}
                  />
                </label>

                <label>
                  End (UTC)
                  <input
                    type="text"
                    value={rangeDraft.end_ts}
                    placeholder="2026-02-02T00:00:00Z"
                    onChange={(event) =>
                      setRangeDraft((current) => ({ ...current, end_ts: event.target.value }))
                    }
                    disabled={!hasSuccessfulCandidates || !artifactsReady}
                  />
                </label>

                <button
                  type="button"
                  className="secondary"
                  onClick={applyRange}
                  disabled={!hasSuccessfulCandidates || !artifactsReady}
                >
                  Apply Range
                </button>
              </div>

              {!hasSuccessfulCandidates ? (
                <div className="chart-empty" style={{ height: 420 }}>
                  <p>
                    No successful candidate runs exist for this experiment. Chart rendering is
                    disabled because there is no artifact-backed run to display.
                  </p>
                </div>
              ) : (
                <>
                  {runError && <ErrorNotice error={runError} compact mode="pro" onRetry={reload} />}
                  {summaryError && (
                    <ErrorNotice error={summaryError} compact mode="pro" onRetry={reload} />
                  )}
                  {ohlcvError && (
                    <ErrorNotice error={ohlcvError} compact mode="pro" onRetry={reload} />
                  )}
                  {markersError && (
                    <ErrorNotice error={markersError} compact mode="pro" onRetry={reload} />
                  )}

                  {!artifactsReady ? (
                    <div className="chart-empty" style={{ height: 420 }}>
                      <p>
                        Selected run artifacts are not ready yet. The chart loads only from run
                        artifacts.
                      </p>
                    </div>
                  ) : ohlcvLoading ? (
                    <div className="chart-empty" style={{ height: 420 }}>
                      <p>Loading baseline OHLCV artifacts...</p>
                    </div>
                  ) : (
                    <CandlestickChart data={candles} markers={markers} height={420} />
                  )}
                </>
              )}

              <div className="chart-status">
                <div>
                  <span>Data range:</span>
                  <strong>
                    {toText(ohlcv?.start_ts)} {"->"} {toText(ohlcv?.end_ts)}
                  </strong>
                </div>
                <div>
                  <span>Bars:</span> <strong>{toText(ohlcv?.count, "0")}</strong>
                </div>
              </div>
            </section>

            <aside className="workspace-sidebar">
              <div className="tab-list">
                {TABS.map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    className={`tab-button ${activeTab === tab.id ? "active" : ""}`}
                    onClick={() => setActiveTab(tab.id)}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              <div className="tab-content">
                {activeTab === "tester" && (
                  <div className="panel-stack">
                    <div className="panel-card">
                      <h3>Comparison Summary</h3>
                      <p className="muted">
                        Values are rendered directly from comparison artifact columns/rows.
                      </p>
                    </div>

                    {comparisonColumns.length === 0 ? (
                      <div className="panel-card">
                        <p className="muted">No comparison columns available.</p>
                      </div>
                    ) : (
                      <div className="panel-card">
                        <div className="table-wrap" style={{ maxHeight: "420px" }}>
                          <table>
                            <thead>
                              <tr>
                                {comparisonColumns.map((column) => (
                                  <th key={column}>
                                    <button
                                      type="button"
                                      className="secondary"
                                      style={{ padding: 0, border: "none", background: "transparent" }}
                                      onClick={() => toggleSort(column)}
                                    >
                                      {column}
                                      {sortConfig.column === column
                                        ? sortConfig.direction === "asc"
                                          ? " ▲"
                                          : " ▼"
                                        : ""}
                                    </button>
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {sortedRows.map((row, index) => {
                                const runId = String(row?.run_id || "");
                                const selectable = Boolean(runId);
                                const selected = selectable && selectedRunId === runId;
                                return (
                                  <tr
                                    key={`${row?.candidate_id || "row"}-${index}`}
                                    className={selected ? "row-selected" : ""}
                                    onClick={() => selectable && setSelectedRunId(runId)}
                                    style={{ cursor: selectable ? "pointer" : "default" }}
                                  >
                                    {comparisonColumns.map((column) => {
                                      const value = row?.[column];
                                      if (column === "run_id" && runId) {
                                        return (
                                          <td key={column}>
                                            <Link href={`/runs/${runId}`}>{runId}</Link>
                                          </td>
                                        );
                                      }
                                      return <td key={column}>{toText(value)}</td>;
                                    })}
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {activeTab === "failures" && (
                  <div className="panel-stack">
                    <div className="panel-card">
                      <h3>Failed Candidates</h3>
                      <p className="muted">Failures are sourced from manifest candidate results.</p>
                    </div>
                    {failedCandidates.length === 0 ? (
                      <div className="panel-card">
                        <p className="muted">No failed candidates recorded.</p>
                      </div>
                    ) : (
                      failedCandidates.map((candidate, index) => {
                        const candidateLabel = candidate?.label || candidate?.candidate_id || `candidate-${index + 1}`;
                        const failure = candidate?.error && typeof candidate.error === "object" ? candidate.error : {};
                        const code = String(failure.code || "UNKNOWN");
                        const message = String(failure.message || "Failure without message");
                        const details = failure.details && typeof failure.details === "object" ? failure.details : {};
                        const mapped = mapErrorPayload({ code, message, details, status: null });

                        return (
                          <div key={`${candidateLabel}-${index}`} className="panel-card">
                            <div className="section-title">
                              <h3>{candidateLabel}</h3>
                              <span className="badge invalid">{code}</span>
                            </div>
                            <p style={{ marginTop: 0 }}>{message}</p>
                            {mapped?.recovery && (
                              <div className="banner info" style={{ marginBottom: "10px" }}>
                                <strong>Recovery</strong>
                                <div>{mapped.recovery}</div>
                              </div>
                            )}
                            <details>
                              <summary className="muted">Details</summary>
                              <pre
                                style={{
                                  marginTop: "8px",
                                  fontSize: "0.75rem",
                                  whiteSpace: "pre-wrap",
                                  wordBreak: "break-word",
                                }}
                              >
                                {JSON.stringify(details, null, 2)}
                              </pre>
                            </details>
                          </div>
                        );
                      })
                    )}
                    <div className="panel-card">
                      <Link href="/experiments">
                        <button type="button" className="secondary">
                          Back to Create
                        </button>
                      </Link>
                    </div>
                  </div>
                )}

                {activeTab === "manifest" && (
                  <div className="panel-stack">
                    <div className="panel-card">
                      <div className="section-title">
                        <h3>Manifest JSON</h3>
                        <button type="button" className="secondary" onClick={copyManifest}>
                          {manifestCopied ? "Copied" : "Copy JSON"}
                        </button>
                      </div>
                      <details open>
                        <summary className="muted">Show manifest</summary>
                        <pre
                          style={{
                            marginTop: "8px",
                            fontSize: "0.75rem",
                            whiteSpace: "pre-wrap",
                            wordBreak: "break-word",
                          }}
                        >
                          {JSON.stringify(manifest || {}, null, 2)}
                        </pre>
                      </details>
                    </div>
                  </div>
                )}
              </div>
            </aside>
          </div>
        )}
      </main>
    </AppShell>
  );
}

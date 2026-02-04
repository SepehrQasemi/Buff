import Link from "next/link";

export default function RunHeader({
  runId,
  runStatus,
  invalidRun,
  missingArtifactsMessage,
  networkError,
  onRetry,
}) {
  const statusLabel = runStatus || "UNKNOWN";
  const statusClass = statusLabel === "OK" ? "ok" : "invalid";

  return (
    <>
      <header>
        <div className="header-title">
          <h1>Run {runId || ""}</h1>
          <span>Decision records, trades, and errors.</span>
        </div>
        <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
          <span className={`badge ${statusClass}`}>{statusLabel}</span>
          <Link className="badge info" href="/runs">
            Back to runs
          </Link>
        </div>
      </header>

      {networkError && (
        <div className="banner" style={{ display: "flex", justifyContent: "space-between" }}>
          <span>{networkError}</span>
          <button onClick={onRetry}>Retry</button>
        </div>
      )}

      {invalidRun && (
        <div className="banner">
          This run is invalid (decision_records.jsonl missing). Sections are disabled.
        </div>
      )}

      {!invalidRun && missingArtifactsMessage && (
        <div className="banner">{missingArtifactsMessage}</div>
      )}
    </>
  );
}

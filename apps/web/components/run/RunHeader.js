import Link from "next/link";
import ErrorNotice from "../ErrorNotice";

export default function RunHeader({
  runId,
  runStatus,
  invalidRun,
  missingArtifactsMessage,
  networkError,
  onRetry,
  onCopyLink,
  linkCopied,
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
          <button className="secondary" onClick={onCopyLink}>
            Copy link
          </button>
          {linkCopied && <span className="badge info">Link copied</span>}
          <Link className="badge info" href="/runs">
            Back to runs
          </Link>
        </div>
      </header>

      {networkError && <ErrorNotice error={networkError} onRetry={onRetry} />}

      {invalidRun && (
        <div className="banner">
          This run is invalid (decision_records.jsonl missing). Sections are disabled.
        </div>
      )}

      {!invalidRun && missingArtifactsMessage && (
        <ErrorNotice error={missingArtifactsMessage} onRetry={onRetry} compact />
      )}
    </>
  );
}

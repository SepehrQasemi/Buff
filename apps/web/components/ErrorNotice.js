import Link from "next/link";
import { normalizeError } from "../lib/errorMapping";

export default function ErrorNotice({ error, onRetry, compact = false, mode = "simple" }) {
  const normalized = normalizeError(error);
  if (!normalized) {
    return null;
  }

  const { title, summary, actions, help, status, code, envelope, recovery } = normalized;
  const showFix = (actions && actions.length > 0) || help;
  const showEnvelope =
    (mode === "simple" || mode === "pro") && envelope && typeof envelope === "object";

  return (
    <div
      className="banner"
      style={{
        display: "grid",
        gap: compact ? "6px" : "10px",
        padding: compact ? "12px" : undefined,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: "12px",
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "grid", gap: compact ? "4px" : "6px" }}>
          <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
            <strong>{title || "Request failed"}</strong>
            {status && <span className="badge info">{`HTTP ${status}`}</span>}
            {code && <span className="badge info">{code}</span>}
          </div>
          {summary && <div className="muted">{summary}</div>}
        </div>
        {onRetry && (
          <button className="secondary" onClick={onRetry}>
            Retry
          </button>
        )}
      </div>

      {showFix && (
        <div style={{ display: "grid", gap: "6px" }}>
          <div className="muted">Troubleshooting / Fix</div>
          {actions?.map((item, index) => (
            <div key={`${item}-${index}`}>{item}</div>
          ))}
          {help && help.href && (
            <Link href={help.href} className="muted">
              {help.label || "View docs"}
            </Link>
          )}
        </div>
      )}

      {recovery && (
        <div style={{ display: "grid", gap: "4px" }}>
          <div className="muted">Recovery</div>
          <div>{recovery}</div>
        </div>
      )}

      {showEnvelope && (
        <details>
          <summary className="muted">Full error envelope</summary>
          <pre
            style={{
              marginTop: "8px",
              fontSize: "0.75rem",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            {JSON.stringify(envelope, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}

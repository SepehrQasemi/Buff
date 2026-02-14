import Link from "next/link";
import { normalizeError } from "../lib/errorMapping";

export default function ErrorNotice({ error, onRetry, compact = false }) {
  const normalized = normalizeError(error);
  if (!normalized) {
    return null;
  }

  const { title, summary, actions, help, status, code } = normalized;
  const showFix = (actions && actions.length > 0) || help;

  return (
    <div
      className="banner"
      style={{
        display: "grid",
        gap: compact ? "6px" : "10px",
        padding: compact ? "12px" : undefined,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: "12px" }}>
        <div>
          <strong>{title || "Request failed"}</strong>
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

      {(status || code) && (
        <div className="muted">
          {code ? `Code: ${code}` : ""}
          {code && status ? " • " : ""}
          {status ? `HTTP ${status}` : ""}
        </div>
      )}
    </div>
  );
}

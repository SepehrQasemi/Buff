import ErrorNotice from "../ErrorNotice";

export default function DecisionsTable({
  items,
  total,
  page,
  pageSize,
  loading,
  error,
  onPageChange,
}) {
  const pageCount = Math.max(1, Math.ceil((total || 0) / (pageSize || 1)));

  return (
    <>
      {error && <ErrorNotice error={error} compact />}
      {loading ? (
        <div>Loading decisions...</div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Symbol</th>
                <th>Action</th>
                <th>Severity</th>
                <th>Reason</th>
                <th>Permission</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row, index) => (
                <tr key={row.decision_id || index}>
                  <td>{row.timestamp || "n/a"}</td>
                  <td>
                    {row.symbol ||
                      (Array.isArray(row.symbols) ? row.symbols.join(", ") : "n/a")}
                  </td>
                  <td>{row.action || "n/a"}</td>
                  <td>{row.severity || row.risk_state || "n/a"}</td>
                  <td>{row.reason_code || row.reason || "n/a"}</td>
                  <td>{row.permission || "n/a"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="toolbar" style={{ justifyContent: "space-between" }}>
        <span style={{ color: "var(--muted)" }}>
          Page {page} of {pageCount}
        </span>
        <div style={{ display: "flex", gap: "8px" }}>
          <button
            className="secondary"
            disabled={page <= 1}
            onClick={() => onPageChange(Math.max(1, page - 1))}
          >
            Prev
          </button>
          <button
            className="secondary"
            disabled={page >= pageCount}
            onClick={() => onPageChange(page + 1)}
          >
            Next
          </button>
        </div>
      </div>
    </>
  );
}

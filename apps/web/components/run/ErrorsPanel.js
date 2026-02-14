import ErrorNotice from "../ErrorNotice";

export default function ErrorsPanel({ payload, loading, error, onExport }) {
  const errors = payload?.errors || payload?.results || [];
  const totalErrors = payload?.total_errors ?? payload?.total ?? errors.length;
  const returnedErrorsCount = payload?.returned_errors_count ?? errors.length;

  return (
    <section className="card">
      <div className="section-title">
        <h2>Errors & Fail-Closed</h2>
        <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
          <p>
            {totalErrors} total / {returnedErrorsCount} returned
          </p>
          {onExport && (
            <>
              <button className="secondary" onClick={() => onExport("csv")}>
                Export CSV
              </button>
              <button className="secondary" onClick={() => onExport("json")}>
                Export JSON
              </button>
            </>
          )}
        </div>
      </div>
      {error && <ErrorNotice error={error} compact />}
      {loading ? (
        <div>Loading errors...</div>
      ) : errors.length === 0 ? (
        <div style={{ color: "var(--muted)" }}>No ERROR/fail-closed records found.</div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Severity</th>
                <th>Reason</th>
                <th>Action</th>
                <th>Permission</th>
              </tr>
            </thead>
            <tbody>
              {errors.map((row, index) => (
                <tr key={row.decision_id || index}>
                  <td>{row.timestamp || "n/a"}</td>
                  <td>{row.severity || row.risk_state || "n/a"}</td>
                  <td>{row.reason_code || row.reason || "n/a"}</td>
                  <td>{row.action || "n/a"}</td>
                  <td>{row.permission || "n/a"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

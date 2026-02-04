export default function ErrorsPanel({ payload, loading, error }) {
  const errors = payload?.errors || payload?.results || [];
  const totalErrors = payload?.total_errors ?? payload?.total ?? errors.length;
  const returnedErrorsCount = payload?.returned_errors_count ?? errors.length;

  return (
    <section className="card">
      <div className="section-title">
        <h2>Errors & Fail-Closed</h2>
        <p>
          {totalErrors} total / {returnedErrorsCount} returned
        </p>
      </div>
      {error && <div className="banner">{error}</div>}
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

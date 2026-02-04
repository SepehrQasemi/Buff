import LineChart from "../LineChart";

export default function TradesPanel({ trades, filters, onChange, loading, error, onExport }) {
  const rows = trades?.results || [];

  const pnlValues = rows.map((row) => Number(row.pnl)).filter((value) => Number.isFinite(value));
  const equityValues = rows
    .map((row) => Number(row.equity))
    .filter((value) => Number.isFinite(value));
  const cumulative = pnlValues.reduce((acc, value) => acc + value, 0);
  const lastEquity = equityValues.length ? equityValues[equityValues.length - 1] : null;

  const tradeStats = trades
    ? {
        count: trades.total ?? rows.length,
        cumulativePnL: cumulative,
        lastEquity,
        chartSeries: equityValues.length
          ? equityValues.map((value, index) => ({ x: index, y: value }))
          : pnlValues.map((value, index) => ({
              x: index,
              y: pnlValues.slice(0, index + 1).reduce((acc, v) => acc + v, 0),
            })),
      }
    : null;

  const update = (updates) => {
    onChange({ ...filters, ...updates });
  };

  return (
    <section className="card" style={{ marginBottom: "24px" }}>
      <div className="section-title">
        <h2>Trades</h2>
        <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
          <p>{trades ? `${trades.total} trades` : "Loading"}</p>
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
      {error && <div className="banner">{error}</div>}
      <div className="toolbar">
        <label>
          Start
          <input
            value={filters.start_ts}
            onChange={(event) => update({ start_ts: event.target.value, page: 1 })}
            placeholder="2026-01-01T00:00:00Z"
          />
        </label>
        <label>
          End
          <input
            value={filters.end_ts}
            onChange={(event) => update({ end_ts: event.target.value, page: 1 })}
            placeholder="2026-01-02T00:00:00Z"
          />
        </label>
        <label>
          Page size
          <select
            value={filters.page_size}
            onChange={(event) => update({ page_size: Number(event.target.value), page: 1 })}
          >
            {[10, 25, 50, 100].map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading && <div>Loading trades...</div>}

      {tradeStats && (
        <div className="grid three" style={{ marginBottom: "16px" }}>
          <div className="kpi">
            <span>Total trades</span>
            <strong>{tradeStats.count}</strong>
          </div>
          <div className="kpi">
            <span>Cumulative PnL</span>
            <strong>{tradeStats.cumulativePnL.toFixed(2)}</strong>
          </div>
          <div className="kpi">
            <span>Last equity</span>
            <strong>
              {tradeStats.lastEquity !== null ? tradeStats.lastEquity.toFixed(2) : "n/a"}
            </strong>
          </div>
        </div>
      )}
      {tradeStats && <LineChart data={tradeStats.chartSeries} />}
      {trades && (
        <div style={{ overflowX: "auto", marginTop: "16px" }}>
          <table>
            <thead>
              <tr>
                {Object.keys(rows?.[0] || {}).map((key) => (
                  <th key={key}>{key}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows?.map((row, index) => (
                <tr key={index}>
                  {Object.keys(rows?.[0] || {}).map((key) => (
                    <td key={key}>{row[key] ?? "n/a"}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="toolbar" style={{ justifyContent: "space-between" }}>
        <span style={{ color: "var(--muted)" }}>Page {filters.page}</span>
        <div style={{ display: "flex", gap: "8px" }}>
          <button
            className="secondary"
            disabled={filters.page <= 1}
            onClick={() => update({ page: Math.max(1, filters.page - 1) })}
          >
            Prev
          </button>
          <button
            className="secondary"
            disabled={!trades || rows.length < filters.page_size}
            onClick={() => update({ page: filters.page + 1 })}
          >
            Next
          </button>
        </div>
      </div>
    </section>
  );
}

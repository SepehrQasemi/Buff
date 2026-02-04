import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import LineChart from "../../components/LineChart";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

const splitList = (value) =>
  value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

const buildQuery = (params) => {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") {
      return;
    }
    if (Array.isArray(value)) {
      value.forEach((item) => query.append(key, item));
      return;
    }
    query.set(key, value);
  });
  return query.toString();
};

export default function RunDashboard() {
  const router = useRouter();
  const { id } = router.query;
  const [run, setRun] = useState(null);
  const [summary, setSummary] = useState(null);
  const [decisions, setDecisions] = useState({ results: [], total: 0, page: 1, page_size: 50 });
  const [trades, setTrades] = useState(null);
  const [errors, setErrors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [filters, setFilters] = useState({
    symbol: "",
    action: "",
    severity: "",
    reason_code: "",
    start_ts: "",
    end_ts: "",
    page: 1,
    page_size: 25,
  });

  const [tradeFilters, setTradeFilters] = useState({
    start_ts: "",
    end_ts: "",
    page: 1,
    page_size: 25,
  });

  const invalidRun = run && run.status !== "OK";

  useEffect(() => {
    if (!id) {
      return;
    }
    let active = true;
    async function loadRun() {
      try {
        const response = await fetch(`${API_BASE}/api/runs`);
        if (!response.ok) {
          throw new Error(`Failed to load runs (${response.status})`);
        }
        const data = await response.json();
        const match = Array.isArray(data) ? data.find((item) => item.id === id) : null;
        if (active) {
          setRun(match || null);
        }
      } catch (err) {
        if (active) {
          setError(err.message || "Failed to load run metadata");
        }
      }
    }
    loadRun();
    return () => {
      active = false;
    };
  }, [id]);

  useEffect(() => {
    if (!id || invalidRun) {
      return;
    }
    let active = true;
    async function loadSummary() {
      try {
        const response = await fetch(`${API_BASE}/api/runs/${id}/summary`);
        if (!response.ok) {
          throw new Error(`Failed to load summary (${response.status})`);
        }
        const data = await response.json();
        if (active) {
          setSummary(data);
        }
      } catch (err) {
        if (active) {
          setError(err.message || "Failed to load summary");
        }
      }
    }
    loadSummary();
    return () => {
      active = false;
    };
  }, [id, invalidRun]);

  const decisionQuery = useMemo(() => {
    return buildQuery({
      symbol: filters.symbol ? splitList(filters.symbol) : undefined,
      action: filters.action ? splitList(filters.action) : undefined,
      severity: filters.severity ? splitList(filters.severity) : undefined,
      reason_code: filters.reason_code ? splitList(filters.reason_code) : undefined,
      start_ts: filters.start_ts || undefined,
      end_ts: filters.end_ts || undefined,
      page: filters.page,
      page_size: filters.page_size,
    });
  }, [filters]);

  useEffect(() => {
    if (!id || invalidRun) {
      return;
    }
    let active = true;
    async function loadDecisions() {
      try {
        const response = await fetch(`${API_BASE}/api/runs/${id}/decisions?${decisionQuery}`);
        if (!response.ok) {
          throw new Error(`Failed to load decisions (${response.status})`);
        }
        const data = await response.json();
        if (active) {
          setDecisions(data);
        }
      } catch (err) {
        if (active) {
          setError(err.message || "Failed to load decisions");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }
    loadDecisions();
    return () => {
      active = false;
    };
  }, [id, decisionQuery, invalidRun]);

  const tradeQuery = useMemo(() => {
    return buildQuery({
      start_ts: tradeFilters.start_ts || undefined,
      end_ts: tradeFilters.end_ts || undefined,
      page: tradeFilters.page,
      page_size: tradeFilters.page_size,
    });
  }, [tradeFilters]);

  useEffect(() => {
    if (!id || !run || invalidRun || !run.has_trades) {
      return;
    }
    let active = true;
    async function loadTrades() {
      try {
        const response = await fetch(`${API_BASE}/api/runs/${id}/trades?${tradeQuery}`);
        if (!response.ok) {
          throw new Error(`Failed to load trades (${response.status})`);
        }
        const data = await response.json();
        if (active) {
          setTrades(data);
        }
      } catch (err) {
        if (active) {
          setError(err.message || "Failed to load trades");
        }
      }
    }
    loadTrades();
    return () => {
      active = false;
    };
  }, [id, run, invalidRun, tradeQuery]);

  useEffect(() => {
    if (!id || invalidRun) {
      return;
    }
    let active = true;
    async function loadErrors() {
      try {
        const response = await fetch(`${API_BASE}/api/runs/${id}/errors`);
        if (!response.ok) {
          throw new Error(`Failed to load errors (${response.status})`);
        }
        const data = await response.json();
        if (active) {
          setErrors(Array.isArray(data.results) ? data.results : []);
        }
      } catch (err) {
        if (active) {
          setError(err.message || "Failed to load errors");
        }
      }
    }
    loadErrors();
    return () => {
      active = false;
    };
  }, [id, invalidRun]);

  const tradeStats = useMemo(() => {
    if (!trades || !Array.isArray(trades.results)) {
      return null;
    }
    const rows = trades.results;
    const pnlValues = rows.map((row) => Number(row.pnl)).filter((value) => Number.isFinite(value));
    const equityValues = rows
      .map((row) => Number(row.equity))
      .filter((value) => Number.isFinite(value));
    const cumulative = pnlValues.reduce((acc, value) => acc + value, 0);
    const lastEquity = equityValues.length ? equityValues[equityValues.length - 1] : null;
    return {
      count: trades.total ?? rows.length,
      cumulativePnL: cumulative,
      lastEquity,
      chartSeries: equityValues.length
        ? equityValues.map((value, index) => ({ x: index, y: value }))
        : pnlValues.map((value, index) => ({
            x: index,
            y: pnlValues.slice(0, index + 1).reduce((acc, v) => acc + v, 0),
          })),
    };
  }, [trades]);

  const decisionPageCount = Math.ceil((decisions.total || 0) / (decisions.page_size || 1));

  return (
    <main>
      <header>
        <div className="header-title">
          <h1>Run {id}</h1>
          <span>Decision records, trades, and errors.</span>
        </div>
        <Link className="badge info" href="/runs">
          Back to runs
        </Link>
      </header>

      {error && <div className="banner">{error}</div>}

      {invalidRun && (
        <div className="banner">
          This run is invalid (decision_records.jsonl missing). Sections are disabled.
        </div>
      )}

      {run && (
        <div className="grid three" style={{ marginBottom: "24px" }}>
          <div className="card fade-up">
            <div className="kpi">
              <span>Created</span>
              <strong>{run.created_at || "n/a"}</strong>
            </div>
          </div>
          <div className="card fade-up" style={{ animationDelay: "60ms" }}>
            <div className="kpi">
              <span>Strategy</span>
              <strong>{run.strategy || "n/a"}</strong>
            </div>
          </div>
          <div className="card fade-up" style={{ animationDelay: "120ms" }}>
            <div className="kpi">
              <span>Symbols</span>
              <strong>{Array.isArray(run.symbols) ? run.symbols.join(", ") : "n/a"}</strong>
            </div>
          </div>
          <div className="card fade-up" style={{ animationDelay: "180ms" }}>
            <div className="kpi">
              <span>Timeframe</span>
              <strong>{run.timeframe || "n/a"}</strong>
            </div>
          </div>
          <div className="card fade-up" style={{ animationDelay: "240ms" }}>
            <div className="kpi">
              <span>Status</span>
              <strong>{run.status}</strong>
            </div>
          </div>
          <div className="card fade-up" style={{ animationDelay: "300ms" }}>
            <div className="kpi">
              <span>Trades</span>
              <strong>{run.has_trades ? "Yes" : "No"}</strong>
            </div>
          </div>
        </div>
      )}

      {!invalidRun && summary && (
        <section className="card" style={{ marginBottom: "24px" }}>
          <div className="section-title">
            <h2>Summary</h2>
            <p>Malformed lines: {summary.malformed_lines_count}</p>
          </div>
          <div className="grid three">
            <div className="kpi">
              <span>Min timestamp</span>
              <strong>{summary.min_timestamp || "n/a"}</strong>
            </div>
            <div className="kpi">
              <span>Max timestamp</span>
              <strong>{summary.max_timestamp || "n/a"}</strong>
            </div>
            <div className="kpi">
              <span>Actions</span>
              <strong>{Object.keys(summary.counts_by_action || {}).length}</strong>
            </div>
          </div>
        </section>
      )}

      {!invalidRun && (
        <section className="card" style={{ marginBottom: "24px" }}>
          <div className="section-title">
            <h2>Decisions</h2>
            <p>{decisions.total} records</p>
          </div>
          <div className="toolbar">
            <label>
              Symbol(s)
              <input
                value={filters.symbol}
                onChange={(event) => setFilters({ ...filters, symbol: event.target.value, page: 1 })}
                placeholder="BTCUSDT, ETHUSDT"
              />
            </label>
            <label>
              Action
              <input
                value={filters.action}
                onChange={(event) => setFilters({ ...filters, action: event.target.value, page: 1 })}
                placeholder="placed, blocked"
              />
            </label>
            <label>
              Severity
              <input
                value={filters.severity}
                onChange={(event) => setFilters({ ...filters, severity: event.target.value, page: 1 })}
                placeholder="ERROR, RED"
              />
            </label>
            <label>
              Reason code
              <input
                value={filters.reason_code}
                onChange={(event) => setFilters({ ...filters, reason_code: event.target.value, page: 1 })}
                placeholder="RISK_BLOCK"
              />
            </label>
            <label>
              Start
              <input
                value={filters.start_ts}
                onChange={(event) => setFilters({ ...filters, start_ts: event.target.value, page: 1 })}
                placeholder="2026-01-01T00:00:00Z"
              />
            </label>
            <label>
              End
              <input
                value={filters.end_ts}
                onChange={(event) => setFilters({ ...filters, end_ts: event.target.value, page: 1 })}
                placeholder="2026-01-02T00:00:00Z"
              />
            </label>
            <label>
              Page size
              <select
                value={filters.page_size}
                onChange={(event) => setFilters({ ...filters, page_size: Number(event.target.value), page: 1 })}
              >
                {[10, 25, 50, 100].map((size) => (
                  <option key={size} value={size}>
                    {size}
                  </option>
                ))}
              </select>
            </label>
            <button className="secondary" onClick={() => setFilters({ ...filters, page: 1 })}>
              Refresh
            </button>
          </div>
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
                  {decisions.results.map((row, index) => (
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
              Page {decisions.page} of {decisionPageCount || 1}
            </span>
            <div style={{ display: "flex", gap: "8px" }}>
              <button
                className="secondary"
                disabled={filters.page <= 1}
                onClick={() => setFilters({ ...filters, page: Math.max(1, filters.page - 1) })}
              >
                Prev
              </button>
              <button
                className="secondary"
                disabled={filters.page >= decisionPageCount}
                onClick={() => setFilters({ ...filters, page: filters.page + 1 })}
              >
                Next
              </button>
            </div>
          </div>
        </section>
      )}

      {!invalidRun && run && run.has_trades && (
        <section className="card" style={{ marginBottom: "24px" }}>
          <div className="section-title">
            <h2>Trades</h2>
            <p>{trades ? `${trades.total} trades` : "Loading"}</p>
          </div>
          <div className="toolbar">
            <label>
              Start
              <input
                value={tradeFilters.start_ts}
                onChange={(event) =>
                  setTradeFilters({ ...tradeFilters, start_ts: event.target.value, page: 1 })
                }
                placeholder="2026-01-01T00:00:00Z"
              />
            </label>
            <label>
              End
              <input
                value={tradeFilters.end_ts}
                onChange={(event) =>
                  setTradeFilters({ ...tradeFilters, end_ts: event.target.value, page: 1 })
                }
                placeholder="2026-01-02T00:00:00Z"
              />
            </label>
            <label>
              Page size
              <select
                value={tradeFilters.page_size}
                onChange={(event) =>
                  setTradeFilters({
                    ...tradeFilters,
                    page_size: Number(event.target.value),
                    page: 1,
                  })
                }
              >
                {[10, 25, 50, 100].map((size) => (
                  <option key={size} value={size}>
                    {size}
                  </option>
                ))}
              </select>
            </label>
          </div>
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
                    {Object.keys(trades.results?.[0] || {}).map((key) => (
                      <th key={key}>{key}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {trades.results?.map((row, index) => (
                    <tr key={index}>
                      {Object.keys(trades.results?.[0] || {}).map((key) => (
                        <td key={key}>{row[key] ?? "n/a"}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="toolbar" style={{ justifyContent: "space-between" }}>
            <span style={{ color: "var(--muted)" }}>
              Page {tradeFilters.page}
            </span>
            <div style={{ display: "flex", gap: "8px" }}>
              <button
                className="secondary"
                disabled={tradeFilters.page <= 1}
                onClick={() =>
                  setTradeFilters({
                    ...tradeFilters,
                    page: Math.max(1, tradeFilters.page - 1),
                  })
                }
              >
                Prev
              </button>
              <button
                className="secondary"
                disabled={!trades || trades.results?.length < tradeFilters.page_size}
                onClick={() => setTradeFilters({ ...tradeFilters, page: tradeFilters.page + 1 })}
              >
                Next
              </button>
            </div>
          </div>
        </section>
      )}

      {!invalidRun && (
        <section className="card">
          <div className="section-title">
            <h2>Errors & Fail-Closed</h2>
            <p>{errors.length} records</p>
          </div>
          {errors.length === 0 ? (
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
      )}
    </main>
  );
}

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import CandlestickChart from "../../components/workspace/CandlestickChart";
import useWorkspace from "../../lib/useWorkspace";

const formatNumber = (value, digits = 2) => {
  if (value === null || value === undefined || value === "") {
    return "n/a";
  }
  const num = Number(value);
  if (!Number.isFinite(num)) {
    return String(value);
  }
  return num.toFixed(digits);
};

const formatPercent = (value) => {
  if (value === null || value === undefined || value === "") {
    return "n/a";
  }
  const num = Number(value);
  if (!Number.isFinite(num)) {
    return String(value);
  }
  return `${(num * 100).toFixed(2)}%`;
};

const formatDate = (value) => (value ? String(value) : "n/a");

const Tabs = [
  { id: "strategy", label: "Strategy" },
  { id: "indicators", label: "Indicators" },
  { id: "trades", label: "Trades" },
  { id: "metrics", label: "Metrics" },
  { id: "timeline", label: "Timeline" },
  { id: "plugins", label: "Plugin Diagnostics" },
  { id: "chat", label: "AI Chat" },
];

export default function ChartWorkspace() {
  const router = useRouter();
  const { id } = router.query;
  const runId = Array.isArray(id) ? id[0] : id;

  const {
    run,
    runError,
    summary,
    summaryError,
    ohlcv,
    ohlcvLoading,
    ohlcvError,
    markers,
    markersError,
    trades,
    tradesError,
    metrics,
    metricsError,
    timeline,
    timelineError,
    activePlugins,
    failedPlugins,
    pluginsError,
    networkError,
    symbol,
    setSymbol,
    timeframe,
    setTimeframe,
    range,
    setRange,
    availableTimeframes,
    reload,
  } = useWorkspace(runId);

  const [activeTab, setActiveTab] = useState("strategy");
  const [selectedTrade, setSelectedTrade] = useState(null);
  const [rangeDraft, setRangeDraft] = useState({ start_ts: "", end_ts: "" });
  const [selectedStrategy, setSelectedStrategy] = useState("");

  useEffect(() => {
    setRangeDraft(range);
  }, [range.start_ts, range.end_ts]);

  const candles = useMemo(() => ohlcv?.candles || [], [ohlcv]);
  const tradeRows = useMemo(() => trades?.results || [], [trades]);
  const activeStrategies = useMemo(
    () => (activePlugins?.strategies ? activePlugins.strategies : []),
    [activePlugins]
  );
  const activeIndicators = useMemo(
    () => (activePlugins?.indicators ? activePlugins.indicators : []),
    [activePlugins]
  );
  const failedStrategies = useMemo(
    () => (failedPlugins?.strategies ? failedPlugins.strategies : []),
    [failedPlugins]
  );
  const failedIndicators = useMemo(
    () => (failedPlugins?.indicators ? failedPlugins.indicators : []),
    [failedPlugins]
  );

  useEffect(() => {
    if (selectedStrategy || activeStrategies.length === 0) {
      return;
    }
    const runStrategy = run?.strategy;
    const match = activeStrategies.find((item) => item.id === runStrategy);
    setSelectedStrategy(match ? match.id : activeStrategies[0].id);
  }, [selectedStrategy, activeStrategies, run]);

  const applyRange = () => {
    setRange({
      start_ts: rangeDraft.start_ts,
      end_ts: rangeDraft.end_ts,
    });
  };

  const risk = summary?.risk || {};
  const provenance = summary?.provenance || {};

  return (
    <main className="workspace-shell" data-testid="chart-workspace">
      <header className="workspace-header">
        <div>
          <div className="workspace-title">Chart Workspace</div>
          <div className="workspace-subtitle">
            Run <strong>{runId || "..."}</strong> - Read-only artifacts view
          </div>
        </div>
        <div className="workspace-actions">
          <button className="secondary" onClick={reload}>
            Refresh
          </button>
        </div>
      </header>

      {networkError && <div className="banner">{networkError}</div>}
      {pluginsError && <div className="banner">{pluginsError}</div>}
      {runError && <div className="banner">{runError}</div>}
      {summaryError && <div className="banner">{summaryError}</div>}
      {ohlcvError && <div className="banner">{ohlcvError}</div>}
      {markersError && <div className="banner">{markersError}</div>}

      <section className="workspace-meta">
        <div className="meta-card">
          <div className="meta-label">Status</div>
          <div className="meta-value">{run?.status || "n/a"}</div>
        </div>
        <div className="meta-card">
          <div className="meta-label">Strategy</div>
          <div className="meta-value">{run?.strategy || "n/a"}</div>
        </div>
        <div className="meta-card">
          <div className="meta-label">Symbols</div>
          <div className="meta-value">
            {Array.isArray(run?.symbols) ? run.symbols.join(", ") : "n/a"}
          </div>
        </div>
        <div className="meta-card">
          <div className="meta-label">Created</div>
          <div className="meta-value">{formatDate(run?.created_at)}</div>
        </div>
        <div className="meta-card">
          <div className="meta-label">Artifacts</div>
          <div className="meta-value">
            {run?.artifacts
              ? Object.entries(run.artifacts)
                  .filter(([, value]) => value)
                  .map(([key]) => key)
                  .join(", ")
              : "n/a"}
          </div>
        </div>
      </section>

      <div className="workspace-body">
        <section className="chart-panel">
          <div className="chart-toolbar">
            <label>
              Symbol
              <select value={symbol} onChange={(event) => setSymbol(event.target.value)}>
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
              >
                {availableTimeframes.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Start (UTC)
              <input
                type="text"
                placeholder="2026-02-01T00:00:00Z"
                value={rangeDraft.start_ts}
                onChange={(event) =>
                  setRangeDraft((current) => ({ ...current, start_ts: event.target.value }))
                }
              />
            </label>
            <label>
              End (UTC)
              <input
                type="text"
                placeholder="2026-02-02T00:00:00Z"
                value={rangeDraft.end_ts}
                onChange={(event) =>
                  setRangeDraft((current) => ({ ...current, end_ts: event.target.value }))
                }
              />
            </label>
            <button className="secondary" onClick={applyRange}>
              Apply Range
            </button>
          </div>

          {ohlcvLoading ? (
            <div className="chart-empty" style={{ height: 420 }}>
              <p>Loading OHLCV artifacts...</p>
            </div>
          ) : (
            <CandlestickChart data={candles} markers={markers} height={420} />
          )}

          <div className="chart-status">
            <div>
              <span>Data range:</span>
              <strong>
                {ohlcv?.start_ts ? ohlcv.start_ts : "n/a"}
                {" -> "}
                {ohlcv?.end_ts ? ` ${ohlcv.end_ts}` : ""}
              </strong>
            </div>
            <div>
              <span>Bars:</span> <strong>{ohlcv?.count ?? 0}</strong>
            </div>
          </div>
        </section>

        <aside className="workspace-sidebar">
          <div className="tab-list">
            {Tabs.map((tab) => (
              <button
                key={tab.id}
                className={`tab-button ${activeTab === tab.id ? "active" : ""}`}
                onClick={() => setActiveTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="tab-content">
            {activeTab === "strategy" && (
              <div className="panel-stack">
                <div className="panel-card">
                  <h3>Strategy Selection</h3>
                  {activeStrategies.length === 0 ? (
                    <p className="muted">
                      No active strategies found. Only validated (PASS) plugins are visible.
                    </p>
                  ) : (
                    <label>
                      Active Strategies
                      <select
                        value={selectedStrategy}
                        onChange={(event) => setSelectedStrategy(event.target.value)}
                      >
                        {activeStrategies.map((strategy) => (
                          <option key={strategy.id} value={strategy.id}>
                            {strategy.name ? `${strategy.name} (${strategy.id})` : strategy.id}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  {run?.strategy &&
                    activeStrategies.length > 0 &&
                    !activeStrategies.some((item) => item.id === run.strategy) && (
                      <p className="inline-warning" style={{ marginTop: "8px" }}>
                        Run strategy is not validated. It is hidden from selection lists.
                      </p>
                    )}
                </div>

                <div className="panel-card">
                  <h3>Strategy Context</h3>
                  <div className="kv-grid">
                    <div>
                      <span>Strategy</span>
                      <strong>{run?.strategy || "n/a"}</strong>
                    </div>
                    <div>
                      <span>Strategy Version</span>
                      <strong>{provenance.strategy_version || "n/a"}</strong>
                    </div>
                    <div>
                      <span>Run ID</span>
                      <strong>{runId || "n/a"}</strong>
                    </div>
                  </div>
                </div>

                <div className="panel-card">
                  <h3>Risk Status</h3>
                  {risk.status !== "ok" && (
                    <div className="inline-warning">
                      Risk artifacts missing or incomplete. UI is fail-closed.
                    </div>
                  )}
                  <div className="kv-grid">
                    <div>
                      <span>Risk Level</span>
                      <strong>{risk.level ?? "n/a"}</strong>
                    </div>
                    <div>
                      <span>State</span>
                      <strong>{risk.state || "n/a"}</strong>
                    </div>
                    <div>
                      <span>Permission</span>
                      <strong>{risk.permission || "n/a"}</strong>
                    </div>
                    <div>
                      <span>Blocked</span>
                      <strong>
                        {risk.blocked === null || risk.blocked === undefined
                          ? "n/a"
                          : risk.blocked
                          ? "Yes"
                          : "No"}
                      </strong>
                    </div>
                    <div>
                      <span>Rule</span>
                      <strong>{risk.rule_id || "n/a"}</strong>
                    </div>
                    <div>
                      <span>Policy Type</span>
                      <strong>{risk.policy_type || "n/a"}</strong>
                    </div>
                    <div>
                      <span>Reason</span>
                      <strong>{risk.reason || "n/a"}</strong>
                    </div>
                  </div>
                </div>

                <div className="panel-card">
                  <h3>Provenance</h3>
                  <div className="kv-grid">
                    <div>
                      <span>Data Snapshot Hash</span>
                      <strong>{provenance.data_snapshot_hash || "n/a"}</strong>
                    </div>
                    <div>
                      <span>Feature Snapshot Hash</span>
                      <strong>{provenance.feature_snapshot_hash || "n/a"}</strong>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {activeTab === "indicators" && (
              <div className="panel-card">
                <h3>Indicators</h3>
                {activeIndicators.length === 0 ? (
                  <p className="muted">
                    No active indicators found. Only validated (PASS) plugins are visible.
                  </p>
                ) : (
                  <div className="kv-grid">
                    {activeIndicators.map((indicator) => (
                      <div key={indicator.id}>
                        <span>{indicator.name || indicator.id}</span>
                        <strong>{indicator.version || "n/a"}</strong>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {activeTab === "trades" && (
              <div className="panel-stack">
                {tradesError ? (
                  <div className="panel-card">
                    <h3>Trades</h3>
                    <p className="inline-warning">{tradesError}</p>
                  </div>
                ) : (
                  <>
                    <div className="panel-card">
                      <h3>Trades</h3>
                      <div className="table-wrap">
                        <table>
                          <thead>
                            <tr>
                              <th>Timestamp</th>
                              <th>Side</th>
                              <th>Price</th>
                              <th>PnL</th>
                            </tr>
                          </thead>
                          <tbody>
                            {tradeRows.length === 0 && (
                              <tr>
                                <td colSpan={4} className="muted">
                                  No trades artifact rows.
                                </td>
                              </tr>
                            )}
                            {tradeRows.map((trade, index) => (
                              <tr
                                key={`${trade.trade_id || index}`}
                                onClick={() => setSelectedTrade(trade)}
                                className={
                                  selectedTrade === trade ? "row-selected" : undefined
                                }
                              >
                                <td>{trade.ts_utc || trade.timestamp || "n/a"}</td>
                                <td>{trade.side || trade.direction || "n/a"}</td>
                                <td>{formatNumber(trade.price)}</td>
                                <td>{formatNumber(trade.pnl)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    <div className="panel-card">
                      <h3>Trade Detail</h3>
                      {selectedTrade ? (
                        <div className="kv-grid">
                          <div>
                            <span>Timestamp</span>
                            <strong>
                              {selectedTrade.ts_utc || selectedTrade.timestamp || "n/a"}
                            </strong>
                          </div>
                          <div>
                            <span>Side</span>
                            <strong>
                              {selectedTrade.side || selectedTrade.direction || "n/a"}
                            </strong>
                          </div>
                          <div>
                            <span>Price</span>
                            <strong>{formatNumber(selectedTrade.price)}</strong>
                          </div>
                          <div>
                            <span>PnL</span>
                            <strong>{formatNumber(selectedTrade.pnl)}</strong>
                          </div>
                          <div>
                            <span>Run ID</span>
                            <strong>{runId || "n/a"}</strong>
                          </div>
                          <div>
                            <span>Strategy Version</span>
                            <strong>{provenance.strategy_version || "n/a"}</strong>
                          </div>
                          <div>
                            <span>Data Snapshot Hash</span>
                            <strong>{provenance.data_snapshot_hash || "n/a"}</strong>
                          </div>
                          <div>
                            <span>Feature Snapshot Hash</span>
                            <strong>{provenance.feature_snapshot_hash || "n/a"}</strong>
                          </div>
                        </div>
                      ) : (
                        <p className="muted">Select a trade row to see details.</p>
                      )}
                    </div>
                  </>
                )}
              </div>
            )}

            {activeTab === "metrics" && (
              <div className="panel-card">
                <h3>Metrics Summary</h3>
                {metricsError ? (
                  <p className="inline-warning">{metricsError}</p>
                ) : metrics ? (
                  <div className="stat-grid">
                    <div className="stat-card">
                      <span>Total Return</span>
                      <strong>{formatPercent(metrics.total_return)}</strong>
                    </div>
                    <div className="stat-card">
                      <span>Max Drawdown</span>
                      <strong>{formatPercent(metrics.max_drawdown)}</strong>
                    </div>
                    <div className="stat-card">
                      <span>Win Rate</span>
                      <strong>{formatPercent(metrics.win_rate)}</strong>
                    </div>
                    <div className="stat-card">
                      <span>Avg Win</span>
                      <strong>{formatNumber(metrics.avg_win)}</strong>
                    </div>
                    <div className="stat-card">
                      <span>Avg Loss</span>
                      <strong>{formatNumber(metrics.avg_loss)}</strong>
                    </div>
                    <div className="stat-card">
                      <span>Trades</span>
                      <strong>{metrics.num_trades ?? "n/a"}</strong>
                    </div>
                  </div>
                ) : (
                  <p className="muted">Metrics artifact not available.</p>
                )}
              </div>
            )}

            {activeTab === "timeline" && (
              <div className="panel-card">
                <h3>Timeline</h3>
                {timelineError ? (
                  <p className="inline-warning">{timelineError}</p>
                ) : (
                  <div className="timeline-list">
                    {timeline.length === 0 && (
                      <p className="muted">No timeline events found in artifacts.</p>
                    )}
                    {timeline.map((event, index) => (
                      <div key={`${event.timestamp}-${index}`} className="timeline-item">
                        <div className="timeline-time">{event.timestamp}</div>
                        <div>
                          <strong>{event.title || event.type}</strong>
                          {event.detail && <p className="muted">{event.detail}</p>}
                          <span className="pill">{event.severity || "INFO"}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {activeTab === "plugins" && (
              <div className="panel-stack">
                <div className="panel-card">
                  <h3>Plugin Diagnostics</h3>
                  <p className="muted">
                    Only failed plugins appear here. Active plugins are eligible for selection.
                  </p>
                </div>
                <div className="panel-card">
                  <h3>Failed Strategies</h3>
                  {failedStrategies.length === 0 ? (
                    <p className="muted">No failed strategies detected.</p>
                  ) : (
                    failedStrategies.map((item) => (
                      <div key={item.id} className="timeline-item">
                        <div className="timeline-time">{item.validated_at_utc || "n/a"}</div>
                        <div>
                          <strong>{item.id}</strong>
                          <p className="muted">Fingerprint: {item.fingerprint || "n/a"}</p>
                          {item.errors?.map((error, index) => (
                            <p key={`${item.id}-${index}`} className="inline-warning">
                              {error.rule_id}: {error.message}
                            </p>
                          ))}
                        </div>
                      </div>
                    ))
                  )}
                </div>
                <div className="panel-card">
                  <h3>Failed Indicators</h3>
                  {failedIndicators.length === 0 ? (
                    <p className="muted">No failed indicators detected.</p>
                  ) : (
                    failedIndicators.map((item) => (
                      <div key={item.id} className="timeline-item">
                        <div className="timeline-time">{item.validated_at_utc || "n/a"}</div>
                        <div>
                          <strong>{item.id}</strong>
                          <p className="muted">Fingerprint: {item.fingerprint || "n/a"}</p>
                          {item.errors?.map((error, index) => (
                            <p key={`${item.id}-${index}`} className="inline-warning">
                              {error.rule_id}: {error.message}
                            </p>
                          ))}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}

            {activeTab === "chat" && (
              <div className="panel-card">
                <h3>AI Chat</h3>
                <p className="muted">
                  Chat is read-only for Phase-1. This shell will host guided flows (add
                  indicator, explain trade) in a later phase.
                </p>
                <div className="chat-shell">
                  <div className="chat-log">Awaiting artifact-backed prompt</div>
                  <input type="text" disabled placeholder="Chat disabled in read-only mode" />
                </div>
              </div>
            )}
          </div>
        </aside>
      </div>
    </main>
  );
}

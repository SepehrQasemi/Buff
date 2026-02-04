import { useRouter } from "next/router";
import DecisionsTable from "../../components/run/DecisionsTable";
import ErrorsPanel from "../../components/run/ErrorsPanel";
import FiltersBar from "../../components/run/FiltersBar";
import RunHeader from "../../components/run/RunHeader";
import SummaryCards from "../../components/run/SummaryCards";
import TradesPanel from "../../components/run/TradesPanel";
import useRunDashboard from "../../lib/useRunDashboard";
import { buildApiUrl } from "../../lib/api";

export default function RunDashboard() {
  const router = useRouter();
  const { id } = router.query;

  const {
    run,
    runError,
    invalidRun,
    summary,
    summaryLoading,
    summaryError,
    decisions,
    decisionsLoading,
    decisionsError,
    trades,
    tradesLoading,
    tradesError,
    errorsPayload,
    errorsLoading,
    errorsError,
    networkError,
    missingArtifactsMessage,
    filters,
    setFilters,
    tradeFilters,
    setTradeFilters,
    decisionParams,
    linkCopied,
    copyLink,
    reload,
  } = useRunDashboard(id);

  const decisionItems = decisions.items || decisions.results || [];

  const handleExport = (section, format) => {
    if (!id) {
      return;
    }
    const params = { format };
    if (section === "decisions") {
      Object.assign(params, { ...decisionParams, page: undefined, page_size: undefined });
    }
    if (section === "trades") {
      Object.assign(params, {
        start_ts: tradeFilters.start_ts || undefined,
        end_ts: tradeFilters.end_ts || undefined,
        page: undefined,
        page_size: undefined,
      });
    }
    const url = buildApiUrl(`/runs/${id}/${section}/export`, params);
    window.location.href = url;
  };

  return (
    <main>
      <RunHeader
        runId={id}
        runStatus={run?.status}
        invalidRun={invalidRun}
        missingArtifactsMessage={missingArtifactsMessage}
        networkError={networkError}
        onRetry={reload}
        onCopyLink={copyLink}
        linkCopied={linkCopied}
      />

      {runError && <div className="banner">{runError}</div>}

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

      {!invalidRun && (
        <SummaryCards summary={summary} loading={summaryLoading} error={summaryError} />
      )}

      {!invalidRun && (
        <section className="card" style={{ marginBottom: "24px" }}>
          <div className="section-title">
            <h2>Decisions</h2>
            <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
              <p>{decisions.total} records</p>
              <button className="secondary" onClick={() => handleExport("decisions", "csv")}>
                Export CSV
              </button>
              <button className="secondary" onClick={() => handleExport("decisions", "json")}>
                Export JSON
              </button>
            </div>
          </div>
          <FiltersBar
            filters={filters}
            onChange={setFilters}
            onRefresh={() => setFilters({ ...filters })}
            disabled={decisionsLoading}
          />
          <DecisionsTable
            items={decisionItems}
            total={decisions.total}
            page={decisions.page}
            pageSize={decisions.page_size}
            loading={decisionsLoading}
            error={decisionsError}
            onPageChange={(page) => setFilters({ ...filters, page })}
          />
        </section>
      )}

      {!invalidRun && run && run.has_trades && (
        <TradesPanel
          trades={trades}
          filters={tradeFilters}
          onChange={setTradeFilters}
          loading={tradesLoading}
          error={tradesError}
          onExport={(format) => handleExport("trades", format)}
        />
      )}

      {!invalidRun && (
        <ErrorsPanel
          payload={errorsPayload}
          loading={errorsLoading}
          error={errorsError}
          onExport={(format) => handleExport("errors", format)}
        />
      )}
    </main>
  );
}

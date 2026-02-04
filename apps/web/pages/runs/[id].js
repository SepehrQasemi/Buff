import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/router";
import DecisionsTable from "../../components/run/DecisionsTable";
import ErrorsPanel from "../../components/run/ErrorsPanel";
import FiltersBar from "../../components/run/FiltersBar";
import RunHeader from "../../components/run/RunHeader";
import SummaryCards from "../../components/run/SummaryCards";
import TradesPanel from "../../components/run/TradesPanel";
import { getDecisions, getErrors, getRuns, getRunSummary, getTrades } from "../../lib/api";

const splitList = (value) =>
  value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

const formatError = (result, fallback) => {
  if (!result) {
    return fallback;
  }
  if (!result.status) {
    return `${fallback}: ${result.error || "API unreachable"}`;
  }
  return `${result.error || fallback} (HTTP ${result.status})`;
};

export default function RunDashboard() {
  const router = useRouter();
  const { id } = router.query;

  const [run, setRun] = useState(null);
  const [runError, setRunError] = useState(null);
  const [summary, setSummary] = useState(null);
  const [summaryError, setSummaryError] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [decisions, setDecisions] = useState({
    results: [],
    items: [],
    total: 0,
    page: 1,
    page_size: 25,
  });
  const [decisionsLoading, setDecisionsLoading] = useState(true);
  const [decisionsError, setDecisionsError] = useState(null);
  const [trades, setTrades] = useState(null);
  const [tradesLoading, setTradesLoading] = useState(false);
  const [tradesError, setTradesError] = useState(null);
  const [errorsPayload, setErrorsPayload] = useState(null);
  const [errorsLoading, setErrorsLoading] = useState(false);
  const [errorsError, setErrorsError] = useState(null);
  const [networkError, setNetworkError] = useState(null);
  const [missingArtifactsMessage, setMissingArtifactsMessage] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);

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

  const decisionsRequestId = useRef(0);
  const tradesRequestId = useRef(0);
  const errorsRequestId = useRef(0);

  const invalidRun = run && run.status !== "OK";

  const decisionParams = useMemo(
    () => ({
      symbol: filters.symbol ? splitList(filters.symbol) : undefined,
      action: filters.action ? splitList(filters.action) : undefined,
      severity: filters.severity ? splitList(filters.severity) : undefined,
      reason_code: filters.reason_code ? splitList(filters.reason_code) : undefined,
      start_ts: filters.start_ts || undefined,
      end_ts: filters.end_ts || undefined,
      page: filters.page,
      page_size: filters.page_size,
    }),
    [filters]
  );

  useEffect(() => {
    if (!id) {
      return;
    }
    let active = true;
    setRunError(null);
    async function loadRun() {
      const result = await getRuns();
      if (!active) {
        return;
      }
      if (!result.ok) {
        setRunError(formatError(result, "Failed to load runs"));
        if (!result.status) {
          setNetworkError("API unreachable. Check that the backend is running.");
        }
        return;
      }
      setNetworkError(null);
      const data = Array.isArray(result.data) ? result.data : [];
      const match = data.find((item) => item.id === id) || null;
      setRun(match);
    }
    loadRun();
    return () => {
      active = false;
    };
  }, [id, reloadToken]);

  useEffect(() => {
    if (!id || invalidRun) {
      return;
    }
    let active = true;
    setSummaryError(null);
    setSummaryLoading(true);
    async function loadSummary() {
      const result = await getRunSummary(id);
      if (!active) {
        return;
      }
      if (!result.ok) {
        setSummaryError(formatError(result, "Failed to load summary"));
        if (result.status === 404) {
          setMissingArtifactsMessage(result.error || "Required artifacts are missing.");
        }
        if (!result.status) {
          setNetworkError("API unreachable. Check that the backend is running.");
        }
        setSummaryLoading(false);
        return;
      }
      setNetworkError(null);
      setMissingArtifactsMessage(null);
      setSummary(result.data);
      setSummaryLoading(false);
    }
    loadSummary();
    return () => {
      active = false;
    };
  }, [id, invalidRun, reloadToken]);

  useEffect(() => {
    if (!id || invalidRun) {
      return;
    }
    const requestId = decisionsRequestId.current + 1;
    decisionsRequestId.current = requestId;
    setDecisionsError(null);
    setDecisionsLoading(true);
    async function loadDecisions() {
      const result = await getDecisions(id, decisionParams);
      if (decisionsRequestId.current !== requestId) {
        return;
      }
      if (!result.ok) {
        setDecisionsError(formatError(result, "Failed to load decisions"));
        if (!result.status) {
          setNetworkError("API unreachable. Check that the backend is running.");
        }
        setDecisionsLoading(false);
        return;
      }
      setNetworkError(null);
      const data = result.data || {};
      const items = data.items || data.results || [];
      setDecisions({
        results: items,
        items,
        total: data.total ?? items.length,
        page: data.page ?? filters.page,
        page_size: data.page_size ?? filters.page_size,
      });
      setDecisionsLoading(false);
    }
    loadDecisions();
  }, [id, invalidRun, decisionParams, reloadToken, filters.page, filters.page_size]);

  useEffect(() => {
    if (!id || !run || invalidRun || !run.has_trades) {
      return;
    }
    const requestId = tradesRequestId.current + 1;
    tradesRequestId.current = requestId;
    setTradesError(null);
    setTradesLoading(true);
    async function loadTrades() {
      const result = await getTrades(id, {
        start_ts: tradeFilters.start_ts || undefined,
        end_ts: tradeFilters.end_ts || undefined,
        page: tradeFilters.page,
        page_size: tradeFilters.page_size,
      });
      if (tradesRequestId.current !== requestId) {
        return;
      }
      if (!result.ok) {
        setTradesError(formatError(result, "Failed to load trades"));
        if (!result.status) {
          setNetworkError("API unreachable. Check that the backend is running.");
        }
        setTradesLoading(false);
        return;
      }
      setNetworkError(null);
      setTrades(result.data);
      setTradesLoading(false);
    }
    loadTrades();
  }, [id, run, invalidRun, tradeFilters, reloadToken]);

  useEffect(() => {
    if (!id || invalidRun) {
      return;
    }
    const requestId = errorsRequestId.current + 1;
    errorsRequestId.current = requestId;
    setErrorsError(null);
    setErrorsLoading(true);
    async function loadErrors() {
      const result = await getErrors(id);
      if (errorsRequestId.current !== requestId) {
        return;
      }
      if (!result.ok) {
        setErrorsError(formatError(result, "Failed to load errors"));
        if (!result.status) {
          setNetworkError("API unreachable. Check that the backend is running.");
        }
        setErrorsLoading(false);
        return;
      }
      setNetworkError(null);
      setErrorsPayload(result.data);
      setErrorsLoading(false);
    }
    loadErrors();
  }, [id, invalidRun, reloadToken]);

  const handleRetry = () => {
    setNetworkError(null);
    setReloadToken((value) => value + 1);
  };

  const decisionItems = decisions.items || decisions.results || [];

  return (
    <main>
      <RunHeader
        runId={id}
        runStatus={run?.status}
        invalidRun={invalidRun}
        missingArtifactsMessage={missingArtifactsMessage}
        networkError={networkError}
        onRetry={handleRetry}
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
            <p>{decisions.total} records</p>
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
        />
      )}

      {!invalidRun && (
        <ErrorsPanel payload={errorsPayload} loading={errorsLoading} error={errorsError} />
      )}
    </main>
  );
}

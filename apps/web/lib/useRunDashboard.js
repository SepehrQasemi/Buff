import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/router";
import { getDecisions, getErrors, getRuns, getRunSummary, getTrades } from "./api";
import { buildQueryString, parseViewState, serializeViewState } from "./urlState";

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

const buildDecisionParams = (filters) => ({
  symbol: filters.symbol ? splitList(filters.symbol) : undefined,
  action: filters.action ? splitList(filters.action) : undefined,
  severity: filters.severity ? splitList(filters.severity) : undefined,
  reason_code: filters.reason_code ? splitList(filters.reason_code) : undefined,
  start_ts: filters.start_ts || undefined,
  end_ts: filters.end_ts || undefined,
  page: filters.page,
  page_size: filters.page_size,
});

export default function useRunDashboard(runId) {
  const router = useRouter();
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
  const [activeTab, setActiveTab] = useState("decisions");
  const [linkCopied, setLinkCopied] = useState(false);

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
  const initializedRef = useRef(false);
  const debounceRef = useRef(null);
  const viewStateRef = useRef({ filters, activeTab });

  const invalidRun = run && run.status !== "OK";
  const decisionParams = useMemo(() => buildDecisionParams(filters), [filters]);

  useEffect(() => {
    viewStateRef.current = { filters, activeTab };
  }, [filters, activeTab]);

  useEffect(() => {
    if (!router.isReady) {
      return;
    }
    const parsed = parseViewState(router.query);
    const incomingQuery = buildQueryString(serializeViewState(parsed));
    const currentQuery = buildQueryString(
      serializeViewState({
        ...viewStateRef.current.filters,
        active_tab: viewStateRef.current.activeTab,
      })
    );
    if (initializedRef.current && incomingQuery === currentQuery) {
      return;
    }
    setFilters((current) => ({
      ...current,
      symbol: parsed.symbol,
      action: parsed.action,
      severity: parsed.severity,
      reason_code: parsed.reason_code,
      start_ts: parsed.start_ts,
      end_ts: parsed.end_ts,
      page: parsed.page,
      page_size: parsed.page_size,
    }));
    setActiveTab(parsed.active_tab);
    initializedRef.current = true;
  }, [router.isReady, router.query]);

  useEffect(() => {
    if (!router.isReady || !initializedRef.current || !runId) {
      return;
    }
    const nextQuery = serializeViewState({ ...filters, active_tab: activeTab });
    const currentQuery = router.asPath.split("?")[1] || "";
    const nextQueryString = buildQueryString(nextQuery);
    const currentQueryString = new URLSearchParams(currentQuery).toString();
    if (currentQueryString === nextQueryString) {
      return;
    }
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    debounceRef.current = setTimeout(() => {
      router.replace(
        { pathname: router.pathname, query: { id: runId, ...nextQuery } },
        undefined,
        { shallow: true }
      );
    }, 300);
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [filters, activeTab, router, runId]);

  useEffect(() => {
    if (!runId) {
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
      const match = data.find((item) => item.id === runId) || null;
      if (!match) {
        setRunError("Run not found in artifacts index.");
      }
      setRun(match);
    }
    loadRun();
    return () => {
      active = false;
    };
  }, [runId, reloadToken]);

  useEffect(() => {
    if (!runId || invalidRun) {
      return;
    }
    let active = true;
    setSummaryError(null);
    setSummaryLoading(true);
    async function loadSummary() {
      const result = await getRunSummary(runId);
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
  }, [runId, invalidRun, reloadToken]);

  useEffect(() => {
    if (!runId || invalidRun) {
      return;
    }
    const requestId = decisionsRequestId.current + 1;
    decisionsRequestId.current = requestId;
    setDecisionsError(null);
    setDecisionsLoading(true);
    async function loadDecisions() {
      const result = await getDecisions(runId, decisionParams);
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
  }, [runId, invalidRun, decisionParams, reloadToken, filters.page, filters.page_size]);

  useEffect(() => {
    if (!runId || !run || invalidRun || !run.has_trades) {
      return;
    }
    const requestId = tradesRequestId.current + 1;
    tradesRequestId.current = requestId;
    setTradesError(null);
    setTradesLoading(true);
    async function loadTrades() {
      const result = await getTrades(runId, {
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
  }, [runId, run, invalidRun, tradeFilters, reloadToken]);

  useEffect(() => {
    if (!runId || invalidRun) {
      return;
    }
    const requestId = errorsRequestId.current + 1;
    errorsRequestId.current = requestId;
    setErrorsError(null);
    setErrorsLoading(true);
    async function loadErrors() {
      const result = await getErrors(runId);
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
  }, [runId, invalidRun, reloadToken]);

  const reload = () => {
    setNetworkError(null);
    setReloadToken((value) => value + 1);
  };

  const copyLink = async () => {
    if (typeof window === "undefined") {
      return;
    }
    const url = window.location.href;
    try {
      await navigator.clipboard.writeText(url);
      setLinkCopied(true);
      setTimeout(() => setLinkCopied(false), 2000);
    } catch (error) {
      setLinkCopied(false);
    }
  };

  return {
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
    activeTab,
    setActiveTab,
    linkCopied,
    copyLink,
    reload,
  };
}

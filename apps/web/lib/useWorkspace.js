import { useEffect, useMemo, useRef, useState } from "react";
import {
  getMetrics,
  getOhlcv,
  getActivePlugins,
  getFailedPlugins,
  getRunSummary,
  getRuns,
  getTimeline,
  getTradeMarkers,
  getTrades,
  invalidateCache,
} from "./api";
import { RUN_NOT_INDEXED_MESSAGE, extractErrorInfo } from "./errors";
import { buildClientError, mapApiErrorDetails } from "./errorMapping";
import {
  buildOhlcvUnavailableMessage,
  deriveAvailableTimeframes,
  pickPreferredTimeframe,
} from "./workspaceState";

const DEFAULT_TRADES_PAGE_SIZE = 250;
const MAX_TRADES_PAGE_SIZE = 500;
const TRANSIENT_RETRY_DELAYS_MS = [250, 500, 1000];
const TRANSIENT_RETRY_MESSAGE = "Temporary filesystem probe failure, retrying...";
const TERMINAL_RUN_STATES = new Set(["COMPLETED", "FAILED", "CORRUPTED", "OK"]);

const isArtifactLifecycleReady = (state) => {
  const normalized = String(state || "").toUpperCase();
  return normalized === "RUNNING" || TERMINAL_RUN_STATES.has(normalized);
};

const isTransientFilesystemFailure = (result) => {
  if (!result || result.ok || result.aborted || result.status !== 503) {
    return false;
  }
  const { code } = extractErrorInfo(result.data);
  if (!code) {
    return true;
  }
  return (
    code === "RUNS_ROOT_UNSET" ||
    code === "RUNS_ROOT_MISSING" ||
    code === "RUNS_ROOT_INVALID" ||
    code === "RUNS_ROOT_NOT_WRITABLE" ||
    code === "REGISTRY_LOCK_TIMEOUT"
  );
};

const waitWithAbort = (delayMs, signal) =>
  new Promise((resolve) => {
    if (signal?.aborted) {
      resolve(false);
      return;
    }
    const timeoutId = setTimeout(() => {
      cleanup();
      resolve(true);
    }, delayMs);
    const onAbort = () => {
      clearTimeout(timeoutId);
      cleanup();
      resolve(false);
    };
    const cleanup = () => signal?.removeEventListener?.("abort", onAbort);
    signal?.addEventListener?.("abort", onAbort, { once: true });
  });

const requestWithTransientRetry = async ({ request, signal, onRetry }) => {
  for (let attempt = 0; ; attempt += 1) {
    const result = await request();
    if (result.ok || result.aborted || !isTransientFilesystemFailure(result)) {
      return result;
    }
    if (attempt >= TRANSIENT_RETRY_DELAYS_MS.length) {
      return result;
    }
    if (onRetry) {
      onRetry();
    }
    const keepGoing = await waitWithAbort(TRANSIENT_RETRY_DELAYS_MS[attempt], signal);
    if (!keepGoing) {
      return { ok: false, aborted: true };
    }
  }
};

export default function useWorkspace(runId, options = {}) {
  const requestedLifecycleState = String(options?.lifecycleState || "").toUpperCase();
  const [run, setRun] = useState(null);
  const [runError, setRunError] = useState(null);
  const [summary, setSummary] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState(null);
  const [ohlcv, setOhlcv] = useState(null);
  const [ohlcvLoading, setOhlcvLoading] = useState(false);
  const [ohlcvError, setOhlcvError] = useState(null);
  const [markers, setMarkers] = useState([]);
  const [markersError, setMarkersError] = useState(null);
  const [trades, setTrades] = useState({ results: [] });
  const [tradesError, setTradesError] = useState(null);
  const [tradesPage, setTradesPage] = useState(1);
  const [tradesPageSize, setTradesPageSize] = useState(DEFAULT_TRADES_PAGE_SIZE);
  const [metrics, setMetrics] = useState(null);
  const [metricsError, setMetricsError] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [timelineError, setTimelineError] = useState(null);
  const [activePlugins, setActivePlugins] = useState({ indicators: [], strategies: [] });
  const [failedPlugins, setFailedPlugins] = useState({ indicators: [], strategies: [] });
  const [pluginsError, setPluginsError] = useState(null);
  const [networkError, setNetworkError] = useState(null);
  const [transientRetryNotice, setTransientRetryNotice] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);

  const [symbol, setSymbol] = useState("");
  const [timeframe, setTimeframe] = useState("");
  const [range, setRange] = useState({ start_ts: "", end_ts: "" });

  const runsRequestId = useRef(0);
  const runsAbortRef = useRef(null);
  const summaryRequestId = useRef(0);
  const summaryAbortRef = useRef(null);
  const ohlcvRequestId = useRef(0);
  const ohlcvAbortRef = useRef(null);
  const markersRequestId = useRef(0);
  const markersAbortRef = useRef(null);
  const tradesRequestId = useRef(0);
  const tradesAbortRef = useRef(null);
  const metricsRequestId = useRef(0);
  const metricsAbortRef = useRef(null);
  const timelineRequestId = useRef(0);
  const timelineAbortRef = useRef(null);
  const pluginsRequestId = useRef(0);
  const pluginsAbortRef = useRef(null);

  const normalizeTradesPageSize = (value) => {
    const parsed = Number.parseInt(value, 10);
    if (!Number.isFinite(parsed) || parsed < 1) {
      return DEFAULT_TRADES_PAGE_SIZE;
    }
    return Math.min(parsed, MAX_TRADES_PAGE_SIZE);
  };

  const normalizeTradesPage = (value) => {
    const parsed = Number.parseInt(value, 10);
    if (!Number.isFinite(parsed) || parsed < 1) {
      return 1;
    }
    return parsed;
  };

  const effectiveTradesPageSize = useMemo(
    () => normalizeTradesPageSize(tradesPageSize),
    [tradesPageSize]
  );
  const effectiveTradesPage = useMemo(
    () => normalizeTradesPage(tradesPage),
    [tradesPage]
  );
  const artifactsReady = useMemo(() => {
    if (requestedLifecycleState) {
      return isArtifactLifecycleReady(requestedLifecycleState);
    }
    return isArtifactLifecycleReady(run?.status);
  }, [requestedLifecycleState, run?.status]);

  useEffect(() => {
    if (effectiveTradesPageSize !== tradesPageSize) {
      setTradesPageSize(effectiveTradesPageSize);
    }
  }, [effectiveTradesPageSize, tradesPageSize]);

  useEffect(() => {
    if (effectiveTradesPage !== tradesPage) {
      setTradesPage(effectiveTradesPage);
    }
  }, [effectiveTradesPage, tradesPage]);

  useEffect(() => {
    if (!runId) {
      return;
    }
    const requestId = runsRequestId.current + 1;
    runsRequestId.current = requestId;
    if (runsAbortRef.current) {
      runsAbortRef.current.abort();
    }
    const controller = new AbortController();
    runsAbortRef.current = controller;
    setRunError(null);
    async function loadRun() {
      const result = await requestWithTransientRetry({
        request: () => getRuns({ signal: controller.signal }),
        signal: controller.signal,
        onRetry: () => setTransientRetryNotice(TRANSIENT_RETRY_MESSAGE),
      });
      if (runsRequestId.current !== requestId || result.aborted) {
        return;
      }
      if (!result.ok) {
        setTransientRetryNotice(null);
        setRun(null);
        setRunError(mapApiErrorDetails(result, "Failed to load runs"));
        return;
      }
      setTransientRetryNotice(null);
      setNetworkError(null);
      const list = Array.isArray(result.data) ? result.data : [];
      const match = list.find((item) => item.id === runId) || null;
      if (!match) {
        setRunError(
          buildClientError({
            title: "Run not found in registry",
            summary: RUN_NOT_INDEXED_MESSAGE,
            actions: [
              "Confirm RUNS_ROOT points to the folder with this run.",
              "Create a new run if the id is missing.",
            ],
          })
        );
        setRun(null);
        return;
      }
      setRunError(null);
      setRun(match);
    }
    loadRun();
    return () => {
      controller.abort();
    };
  }, [runId, reloadToken]);

  useEffect(() => {
    if (!run || !runId) {
      return;
    }
    if (!symbol && Array.isArray(run.symbols) && run.symbols.length) {
      setSymbol(run.symbols[0]);
    }
  }, [run, runId, symbol]);

  const availableTimeframes = useMemo(
    () => deriveAvailableTimeframes(summary, run?.timeframe),
    [summary, run?.timeframe]
  );

  useEffect(() => {
    if (!runId) {
      return;
    }
    const preferred = pickPreferredTimeframe({
      currentTimeframe: timeframe,
      runTimeframe: run?.timeframe,
      availableTimeframes,
    });
    if (preferred !== timeframe) {
      setTimeframe(preferred);
    }
  }, [availableTimeframes, run?.timeframe, runId, timeframe]);

  useEffect(() => {
    if (!runId) {
      return;
    }
    if (!artifactsReady) {
      setSummaryLoading(false);
      return;
    }
    const requestId = summaryRequestId.current + 1;
    summaryRequestId.current = requestId;
    if (summaryAbortRef.current) {
      summaryAbortRef.current.abort();
    }
    const controller = new AbortController();
    summaryAbortRef.current = controller;
    setSummaryLoading(true);
    setSummaryError(null);
    setSummary(null);
    setTransientRetryNotice(null);
    async function loadSummary() {
      const result = await requestWithTransientRetry({
        request: () =>
          getRunSummary(runId, {
            signal: controller.signal,
            cache: true,
          }),
        signal: controller.signal,
        onRetry: () => setTransientRetryNotice(TRANSIENT_RETRY_MESSAGE),
      });
      if (summaryRequestId.current !== requestId || result.aborted) {
        return;
      }
      if (!result.ok) {
        setTransientRetryNotice(null);
        setSummary(null);
        setSummaryError(mapApiErrorDetails(result, "Failed to load run summary"));
        setSummaryLoading(false);
        return;
      }
      setTransientRetryNotice(null);
      setNetworkError(null);
      setSummary(result.data);
      setSummaryLoading(false);
    }
    loadSummary();
    return () => {
      controller.abort();
    };
  }, [artifactsReady, runId, reloadToken]);

  useEffect(() => {
    if (!runId) {
      return;
    }
    if (!artifactsReady) {
      setOhlcvLoading(false);
      return;
    }
    const currentId = ohlcvRequestId.current + 1;
    ohlcvRequestId.current = currentId;
    if (ohlcvAbortRef.current) {
      ohlcvAbortRef.current.abort();
    }
    const controller = new AbortController();
    ohlcvAbortRef.current = controller;
    setOhlcvError(null);
    async function loadOhlcv() {
      setOhlcvLoading(true);
      if (!availableTimeframes.includes(timeframe)) {
        const fallbackTimeframe = availableTimeframes[0] || "1m";
        setOhlcvError(
          buildClientError({
            title: "OHLCV timeframe unavailable",
            summary: buildOhlcvUnavailableMessage(timeframe, availableTimeframes),
            actions: [
              "Select a timeframe that exists in run artifacts.",
              "Regenerate artifacts if additional timeframes are required.",
            ],
          })
        );
        if (fallbackTimeframe !== timeframe) {
          setTimeframe(fallbackTimeframe);
        }
        setOhlcvLoading(false);
        return;
      }
      const params = {
        symbol: symbol || undefined,
        timeframe: timeframe || undefined,
        start_ts: range.start_ts || undefined,
        end_ts: range.end_ts || undefined,
        limit: 2000,
      };
      const result = await requestWithTransientRetry({
        request: () =>
          getOhlcv(runId, params, {
            signal: controller.signal,
            cache: true,
          }),
        signal: controller.signal,
        onRetry: () => setTransientRetryNotice(TRANSIENT_RETRY_MESSAGE),
      });
      if (ohlcvRequestId.current !== currentId || result.aborted) {
        return;
      }
      if (!result.ok) {
        const { code } = extractErrorInfo(result.data);
        if (result.status === 404 && code === "ohlcv_missing") {
          const fallbackTimeframe = availableTimeframes[0] || "1m";
          setOhlcvError(
            buildClientError({
              title: "OHLCV timeframe unavailable",
              summary: buildOhlcvUnavailableMessage(timeframe, availableTimeframes),
              actions: [
                "Switch to one of the available timeframes.",
                "Regenerate run artifacts if this timeframe is required.",
              ],
            })
          );
          if (fallbackTimeframe !== timeframe) {
            setTimeframe(fallbackTimeframe);
          }
          setOhlcvLoading(false);
          return;
        }
        setTransientRetryNotice(null);
        setOhlcvError(mapApiErrorDetails(result, "Failed to load OHLCV"));
        setOhlcvLoading(false);
        return;
      }
      setTransientRetryNotice(null);
      setOhlcv(result.data);
      setOhlcvLoading(false);
    }
    if (timeframe) {
      loadOhlcv();
    } else {
      setOhlcvLoading(false);
    }
    return () => {
      controller.abort();
    };
  }, [artifactsReady, runId, symbol, timeframe, range, reloadToken, availableTimeframes]);

  useEffect(() => {
    if (!runId) {
      return;
    }
    if (!artifactsReady) {
      return;
    }
    const requestId = markersRequestId.current + 1;
    markersRequestId.current = requestId;
    if (markersAbortRef.current) {
      markersAbortRef.current.abort();
    }
    const controller = new AbortController();
    markersAbortRef.current = controller;
    async function loadMarkers() {
      const params = {
        start_ts: range.start_ts || undefined,
        end_ts: range.end_ts || undefined,
      };
      const result = await requestWithTransientRetry({
        request: () =>
          getTradeMarkers(runId, params, {
            signal: controller.signal,
            cache: true,
          }),
        signal: controller.signal,
        onRetry: () => setTransientRetryNotice(TRANSIENT_RETRY_MESSAGE),
      });
      if (markersRequestId.current !== requestId || result.aborted) {
        return;
      }
      if (!result.ok) {
        setTransientRetryNotice(null);
        setMarkersError(mapApiErrorDetails(result, "Failed to load trade markers"));
        return;
      }
      setTransientRetryNotice(null);
      setMarkers(Array.isArray(result.data?.markers) ? result.data.markers : []);
      setMarkersError(null);
    }
    loadMarkers();
    return () => {
      controller.abort();
    };
  }, [artifactsReady, runId, range, reloadToken]);

  useEffect(() => {
    if (!runId) {
      return;
    }
    setTradesPage(1);
  }, [runId]);

  useEffect(() => {
    if (!runId) {
      return;
    }
    setTradesPage(1);
  }, [effectiveTradesPageSize, runId]);

  useEffect(() => {
    const total = trades?.total;
    if (total === null || total === undefined) {
      return;
    }
    const maxPage = Math.max(1, Math.ceil(total / effectiveTradesPageSize));
    if (effectiveTradesPage > maxPage) {
      setTradesPage(maxPage);
    }
  }, [trades?.total, effectiveTradesPage, effectiveTradesPageSize]);

  useEffect(() => {
    if (!runId) {
      return;
    }
    if (!artifactsReady) {
      return;
    }
    const requestId = tradesRequestId.current + 1;
    tradesRequestId.current = requestId;
    if (tradesAbortRef.current) {
      tradesAbortRef.current.abort();
    }
    const controller = new AbortController();
    tradesAbortRef.current = controller;
    async function loadTrades() {
      const result = await requestWithTransientRetry({
        request: () =>
          getTrades(
            runId,
            { page: effectiveTradesPage, page_size: effectiveTradesPageSize },
            {
              signal: controller.signal,
              cache: true,
            }
          ),
        signal: controller.signal,
        onRetry: () => setTransientRetryNotice(TRANSIENT_RETRY_MESSAGE),
      });
      if (tradesRequestId.current !== requestId || result.aborted) {
        return;
      }
      if (!result.ok) {
        setTransientRetryNotice(null);
        setTradesError(mapApiErrorDetails(result, "Failed to load trades"));
        return;
      }
      setTransientRetryNotice(null);
      setTrades(result.data || { results: [] });
      setTradesError(null);
    }
    loadTrades();
    return () => {
      controller.abort();
    };
  }, [artifactsReady, runId, reloadToken, effectiveTradesPage, effectiveTradesPageSize]);

  useEffect(() => {
    if (!runId) {
      return;
    }
    if (!artifactsReady) {
      return;
    }
    const requestId = metricsRequestId.current + 1;
    metricsRequestId.current = requestId;
    if (metricsAbortRef.current) {
      metricsAbortRef.current.abort();
    }
    const controller = new AbortController();
    metricsAbortRef.current = controller;
    async function loadMetrics() {
      const result = await requestWithTransientRetry({
        request: () =>
          getMetrics(runId, {
            signal: controller.signal,
            cache: true,
          }),
        signal: controller.signal,
        onRetry: () => setTransientRetryNotice(TRANSIENT_RETRY_MESSAGE),
      });
      if (metricsRequestId.current !== requestId || result.aborted) {
        return;
      }
      if (!result.ok) {
        setTransientRetryNotice(null);
        setMetricsError(mapApiErrorDetails(result, "Failed to load metrics"));
        return;
      }
      setTransientRetryNotice(null);
      setMetrics(result.data);
      setMetricsError(null);
    }
    loadMetrics();
    return () => {
      controller.abort();
    };
  }, [artifactsReady, runId, reloadToken]);

  useEffect(() => {
    if (!runId) {
      return;
    }
    if (!artifactsReady) {
      return;
    }
    const requestId = timelineRequestId.current + 1;
    timelineRequestId.current = requestId;
    if (timelineAbortRef.current) {
      timelineAbortRef.current.abort();
    }
    const controller = new AbortController();
    timelineAbortRef.current = controller;
    async function loadTimeline() {
      const result = await requestWithTransientRetry({
        request: () =>
          getTimeline(
            runId,
            { source: "auto" },
            {
              signal: controller.signal,
              cache: true,
            }
          ),
        signal: controller.signal,
        onRetry: () => setTransientRetryNotice(TRANSIENT_RETRY_MESSAGE),
      });
      if (timelineRequestId.current !== requestId || result.aborted) {
        return;
      }
      if (!result.ok) {
        setTransientRetryNotice(null);
        setTimelineError(mapApiErrorDetails(result, "Failed to load timeline"));
        return;
      }
      setTransientRetryNotice(null);
      const events = Array.isArray(result.data?.events) ? result.data.events : [];
      setTimeline(events);
      setTimelineError(null);
    }
    loadTimeline();
    return () => {
      controller.abort();
    };
  }, [artifactsReady, runId, reloadToken]);

  useEffect(() => {
    if (!runId) {
      return;
    }
    if (!artifactsReady) {
      return;
    }
    const requestId = pluginsRequestId.current + 1;
    pluginsRequestId.current = requestId;
    if (pluginsAbortRef.current) {
      pluginsAbortRef.current.abort();
    }
    const controller = new AbortController();
    pluginsAbortRef.current = controller;
    async function loadPlugins() {
      const [activeResult, failedResult] = await Promise.all([
        requestWithTransientRetry({
          request: () => getActivePlugins({ signal: controller.signal }),
          signal: controller.signal,
          onRetry: () => setTransientRetryNotice(TRANSIENT_RETRY_MESSAGE),
        }),
        requestWithTransientRetry({
          request: () => getFailedPlugins({ signal: controller.signal }),
          signal: controller.signal,
          onRetry: () => setTransientRetryNotice(TRANSIENT_RETRY_MESSAGE),
        }),
      ]);
      if (
        pluginsRequestId.current !== requestId ||
        activeResult.aborted ||
        failedResult.aborted
      ) {
        return;
      }
      const normalize = (payload) => ({
        indicators: Array.isArray(payload?.indicators) ? payload.indicators : [],
        strategies: Array.isArray(payload?.strategies) ? payload.strategies : [],
      });

      if (!activeResult.ok) {
        setTransientRetryNotice(null);
        setPluginsError(mapApiErrorDetails(activeResult, "Failed to load active plugins"));
      } else {
        setTransientRetryNotice(null);
        setActivePlugins(normalize(activeResult.data));
        setPluginsError(null);
      }

      if (!failedResult.ok) {
        setTransientRetryNotice(null);
        setPluginsError(mapApiErrorDetails(failedResult, "Failed to load plugin diagnostics"));
      } else {
        setTransientRetryNotice(null);
        setFailedPlugins(normalize(failedResult.data));
      }
    }
    loadPlugins();
    return () => {
      controller.abort();
    };
  }, [artifactsReady, runId, reloadToken]);

  const reload = () => {
    invalidateCache({ runId });
    setReloadToken((value) => value + 1);
  };

  return {
    run,
    runError,
    summary,
    summaryLoading,
    summaryError,
    ohlcv,
    ohlcvLoading,
    ohlcvError,
    markers,
    markersError,
    trades,
    tradesError,
    tradesPage: effectiveTradesPage,
    setTradesPage,
    tradesPageSize: effectiveTradesPageSize,
    setTradesPageSize,
    metrics,
    metricsError,
    timeline,
    timelineError,
    activePlugins,
    failedPlugins,
    pluginsError,
    networkError,
    transientRetryNotice,
    symbol,
    setSymbol,
    timeframe,
    setTimeframe,
    range,
    setRange,
    availableTimeframes,
    artifactsReady,
    reload,
  };
}

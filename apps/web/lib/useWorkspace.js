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
import { RUN_NOT_INDEXED_MESSAGE } from "./errors";
import { buildClientError, mapApiErrorDetails } from "./errorMapping";

const DEFAULT_TIMEFRAMES = [
  "1m",
  "5m",
  "15m",
  "30m",
  "1h",
  "2h",
  "4h",
  "1d",
  "1w",
  "1M",
];
const DEFAULT_TRADES_PAGE_SIZE = 250;
const MAX_TRADES_PAGE_SIZE = 500;

export default function useWorkspace(runId) {
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
      const result = await getRuns({ signal: controller.signal });
      if (runsRequestId.current !== requestId || result.aborted) {
        return;
      }
      if (!result.ok) {
        setRunError(mapApiErrorDetails(result, "Failed to load runs"));
        return;
      }
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
      }
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
    if (!timeframe && run.timeframe) {
      setTimeframe(run.timeframe);
    }
    if (!timeframe && !run.timeframe) {
      setTimeframe("1m");
    }
  }, [run, runId, symbol, timeframe]);

  useEffect(() => {
    if (!runId) {
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
    async function loadSummary() {
      const result = await getRunSummary(runId, {
        signal: controller.signal,
        cache: true,
      });
      if (summaryRequestId.current !== requestId || result.aborted) {
        return;
      }
      if (!result.ok) {
        setSummaryError(mapApiErrorDetails(result, "Failed to load run summary"));
        setSummaryLoading(false);
        return;
      }
      setNetworkError(null);
      setSummary(result.data);
      setSummaryLoading(false);
    }
    loadSummary();
    return () => {
      controller.abort();
    };
  }, [runId, reloadToken]);

  useEffect(() => {
    if (!runId) {
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
      const params = {
        symbol: symbol || undefined,
        timeframe: timeframe || undefined,
        start_ts: range.start_ts || undefined,
        end_ts: range.end_ts || undefined,
        limit: 2000,
      };
      const result = await getOhlcv(runId, params, {
        signal: controller.signal,
        cache: true,
      });
      if (ohlcvRequestId.current !== currentId || result.aborted) {
        return;
      }
      if (!result.ok) {
        setOhlcvError(mapApiErrorDetails(result, "Failed to load OHLCV"));
        setOhlcvLoading(false);
        return;
      }
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
  }, [runId, symbol, timeframe, range, reloadToken]);

  useEffect(() => {
    if (!runId) {
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
      const result = await getTradeMarkers(runId, params, {
        signal: controller.signal,
        cache: true,
      });
      if (markersRequestId.current !== requestId || result.aborted) {
        return;
      }
      if (!result.ok) {
        setMarkersError(mapApiErrorDetails(result, "Failed to load trade markers"));
        return;
      }
      setMarkers(Array.isArray(result.data?.markers) ? result.data.markers : []);
      setMarkersError(null);
    }
    loadMarkers();
    return () => {
      controller.abort();
    };
  }, [runId, range, reloadToken]);

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
    const requestId = tradesRequestId.current + 1;
    tradesRequestId.current = requestId;
    if (tradesAbortRef.current) {
      tradesAbortRef.current.abort();
    }
    const controller = new AbortController();
    tradesAbortRef.current = controller;
    async function loadTrades() {
      const result = await getTrades(
        runId,
        { page: effectiveTradesPage, page_size: effectiveTradesPageSize },
        {
          signal: controller.signal,
          cache: true,
        }
      );
      if (tradesRequestId.current !== requestId || result.aborted) {
        return;
      }
      if (!result.ok) {
        setTradesError(mapApiErrorDetails(result, "Failed to load trades"));
        return;
      }
      setTrades(result.data || { results: [] });
      setTradesError(null);
    }
    loadTrades();
    return () => {
      controller.abort();
    };
  }, [runId, reloadToken, effectiveTradesPage, effectiveTradesPageSize]);

  useEffect(() => {
    if (!runId) {
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
      const result = await getMetrics(runId, {
        signal: controller.signal,
        cache: true,
      });
      if (metricsRequestId.current !== requestId || result.aborted) {
        return;
      }
      if (!result.ok) {
        setMetricsError(mapApiErrorDetails(result, "Failed to load metrics"));
        return;
      }
      setMetrics(result.data);
      setMetricsError(null);
    }
    loadMetrics();
    return () => {
      controller.abort();
    };
  }, [runId, reloadToken]);

  useEffect(() => {
    if (!runId) {
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
      const result = await getTimeline(
        runId,
        { source: "auto" },
        {
          signal: controller.signal,
          cache: true,
        }
      );
      if (timelineRequestId.current !== requestId || result.aborted) {
        return;
      }
      if (!result.ok) {
        setTimelineError(mapApiErrorDetails(result, "Failed to load timeline"));
        return;
      }
      const events = Array.isArray(result.data?.events) ? result.data.events : [];
      setTimeline(events);
      setTimelineError(null);
    }
    loadTimeline();
    return () => {
      controller.abort();
    };
  }, [runId, reloadToken]);

  useEffect(() => {
    if (!runId) {
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
        getActivePlugins({ signal: controller.signal }),
        getFailedPlugins({ signal: controller.signal }),
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
        setPluginsError(mapApiErrorDetails(activeResult, "Failed to load active plugins"));
      } else {
        setActivePlugins(normalize(activeResult.data));
        setPluginsError(null);
      }

      if (!failedResult.ok) {
        setPluginsError(mapApiErrorDetails(failedResult, "Failed to load plugin diagnostics"));
      } else {
        setFailedPlugins(normalize(failedResult.data));
      }
    }
    loadPlugins();
    return () => {
      controller.abort();
    };
  }, [runId, reloadToken]);

  const availableTimeframes = useMemo(() => {
    if (run?.timeframe && !DEFAULT_TIMEFRAMES.includes(run.timeframe)) {
      return [run.timeframe, ...DEFAULT_TIMEFRAMES];
    }
    return DEFAULT_TIMEFRAMES;
  }, [run]);

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
    symbol,
    setSymbol,
    timeframe,
    setTimeframe,
    range,
    setRange,
    availableTimeframes,
    reload,
  };
}

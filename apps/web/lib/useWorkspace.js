import { useEffect, useMemo, useRef, useState } from "react";
import {
  getMetrics,
  getOhlcv,
  getRunSummary,
  getRuns,
  getTimeline,
  getTradeMarkers,
  getTrades,
} from "./api";

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

const formatError = (result, fallback) => {
  if (!result) {
    return fallback;
  }
  if (!result.status) {
    return `${fallback}: ${result.error || "API unreachable"}`;
  }
  return `${result.error || fallback} (HTTP ${result.status})`;
};

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
  const [metrics, setMetrics] = useState(null);
  const [metricsError, setMetricsError] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [timelineError, setTimelineError] = useState(null);
  const [networkError, setNetworkError] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);

  const [symbol, setSymbol] = useState("");
  const [timeframe, setTimeframe] = useState("");
  const [range, setRange] = useState({ start_ts: "", end_ts: "" });

  const requestId = useRef(0);

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
      const list = Array.isArray(result.data) ? result.data : [];
      const match = list.find((item) => item.id === runId) || null;
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
    let active = true;
    setSummaryLoading(true);
    setSummaryError(null);
    async function loadSummary() {
      const result = await getRunSummary(runId);
      if (!active) {
        return;
      }
      if (!result.ok) {
        setSummaryError(formatError(result, "Failed to load run summary"));
        if (!result.status) {
          setNetworkError("API unreachable. Check that the backend is running.");
        }
        setSummaryLoading(false);
        return;
      }
      setNetworkError(null);
      setSummary(result.data);
      setSummaryLoading(false);
    }
    loadSummary();
    return () => {
      active = false;
    };
  }, [runId, reloadToken]);

  useEffect(() => {
    if (!runId) {
      return;
    }
    const currentId = requestId.current + 1;
    requestId.current = currentId;
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
      const result = await getOhlcv(runId, params);
      if (requestId.current !== currentId) {
        return;
      }
      if (!result.ok) {
        setOhlcvError(formatError(result, "Failed to load OHLCV"));
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
  }, [runId, symbol, timeframe, range, reloadToken]);

  useEffect(() => {
    if (!runId) {
      return;
    }
    async function loadMarkers() {
      const params = {
        start_ts: range.start_ts || undefined,
        end_ts: range.end_ts || undefined,
      };
      const result = await getTradeMarkers(runId, params);
      if (!result.ok) {
        setMarkersError(formatError(result, "Failed to load trade markers"));
        return;
      }
      setMarkers(Array.isArray(result.data?.markers) ? result.data.markers : []);
      setMarkersError(null);
    }
    loadMarkers();
  }, [runId, range, reloadToken]);

  useEffect(() => {
    if (!runId) {
      return;
    }
    async function loadTrades() {
      const result = await getTrades(runId, { page: 1, page_size: 250 });
      if (!result.ok) {
        setTradesError(formatError(result, "Failed to load trades"));
        return;
      }
      setTrades(result.data || { results: [] });
      setTradesError(null);
    }
    loadTrades();
  }, [runId, reloadToken]);

  useEffect(() => {
    if (!runId) {
      return;
    }
    async function loadMetrics() {
      const result = await getMetrics(runId);
      if (!result.ok) {
        setMetricsError(formatError(result, "Failed to load metrics"));
        return;
      }
      setMetrics(result.data);
      setMetricsError(null);
    }
    loadMetrics();
  }, [runId, reloadToken]);

  useEffect(() => {
    if (!runId) {
      return;
    }
    async function loadTimeline() {
      const result = await getTimeline(runId, { source: "auto" });
      if (!result.ok) {
        setTimelineError(formatError(result, "Failed to load timeline"));
        return;
      }
      const events = Array.isArray(result.data?.events) ? result.data.events : [];
      setTimeline(events);
      setTimelineError(null);
    }
    loadTimeline();
  }, [runId, reloadToken]);

  const availableTimeframes = useMemo(() => {
    if (run?.timeframe && !DEFAULT_TIMEFRAMES.includes(run.timeframe)) {
      return [run.timeframe, ...DEFAULT_TIMEFRAMES];
    }
    return DEFAULT_TIMEFRAMES;
  }, [run]);

  const reload = () => setReloadToken((value) => value + 1);

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
    metrics,
    metricsError,
    timeline,
    timelineError,
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

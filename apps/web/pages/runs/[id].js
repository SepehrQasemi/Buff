import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import AppShell from "../../components/AppShell";
import CandlestickChart from "../../components/workspace/CandlestickChart";
import ErrorNotice from "../../components/ErrorNotice";
import { exportRunReport, getChatModes, getRunStatus, postChat } from "../../lib/api";
import { MISSING_RUN_ID_MESSAGE } from "../../lib/errors";
import { buildClientError, mapApiErrorDetails } from "../../lib/errorMapping";
import { evaluateRiskPanelState } from "../../lib/workspaceState";
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

const formatMetricValue = (value) => {
  if (value === null || value === undefined || value === "") {
    return "n/a";
  }
  return String(value);
};

const normalizeTimelineSeverity = (value) => {
  const normalized =
    value === null || value === undefined || value === ""
      ? "INFO"
      : String(value).toUpperCase();
  if (normalized.startsWith("ERR")) {
    return { filterBucket: "ERROR", label: "ERROR", alwaysVisible: false };
  }
  if (normalized.startsWith("WARN")) {
    return { filterBucket: "WARN", label: "WARN", alwaysVisible: false };
  }
  if (normalized.startsWith("INFO")) {
    return { filterBucket: "INFO", label: "INFO", alwaysVisible: false };
  }
  return {
    filterBucket: "INFO",
    label: normalized,
    alwaysVisible: true,
  };
};

const extractTimelineDate = (value) => {
  if (!value) {
    return "Unknown date";
  }
  const text = String(value);
  const dateToken = text.includes("T") ? text.split("T")[0] : text.split(" ")[0];
  return /^\d{4}-\d{2}-\d{2}$/.test(dateToken) ? dateToken : "Unknown date";
};

const formatDate = (value) => (value ? String(value) : "n/a");

const normalizeParams = (params) => (Array.isArray(params) ? params : []);
const hasParamDefault = (param) =>
  Boolean(param && Object.prototype.hasOwnProperty.call(param, "default"));

const buildParamDefaults = (params) =>
  normalizeParams(params).reduce((acc, param) => {
    if (!param || !param.name) {
      return acc;
    }
    if (hasParamDefault(param) && param.default !== null) {
      acc[param.name] = param.default;
    }
    return acc;
  }, {});

const Tabs = [
  { id: "strategy", label: "Strategy" },
  { id: "indicators", label: "Indicators" },
  { id: "trades", label: "Trades" },
  { id: "metrics", label: "Metrics" },
  { id: "timeline", label: "Timeline" },
  { id: "plugins", label: "Plugin Diagnostics" },
  { id: "chat", label: "AI Chat" },
];

const DEFAULT_CHAT_MODES = [
  { id: "add_indicator", label: "Add Indicator" },
  { id: "add_strategy", label: "Add Strategy" },
  { id: "review_plugin", label: "Review Plugin" },
  { id: "troubleshoot_errors", label: "Troubleshoot Errors" },
  { id: "explain_trade", label: "Explain Trade" },
];
const TRADE_PAGE_SIZES = [50, 100, 250, 500];

const parseCsv = (value) =>
  String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

const TERMINAL_RUN_STATES = new Set(["COMPLETED", "FAILED", "CORRUPTED", "OK"]);

const runStateBadgeKind = (state) => {
  const normalized = String(state || "").toUpperCase();
  if (normalized === "COMPLETED" || normalized === "OK") {
    return "ok";
  }
  if (normalized === "FAILED" || normalized === "CORRUPTED") {
    return "invalid";
  }
  return "info";
};

const lifecycleSummary = (state) => {
  const normalized = String(state || "").toUpperCase();
  if (!normalized) {
    return "Waiting for lifecycle status...";
  }
  if (normalized === "CREATED") {
    return "Run created. Waiting for runtime initialization.";
  }
  if (normalized === "VALIDATED") {
    return "Validation complete. Waiting for runtime start.";
  }
  if (normalized === "RUNNING") {
    return "Run is active. Loading artifact surfaces.";
  }
  if (TERMINAL_RUN_STATES.has(normalized)) {
    return "Run reached terminal state. Artifact surfaces are available.";
  }
  return `Lifecycle state: ${normalized}.`;
};

export default function ChartWorkspace() {
  const router = useRouter();
  const { id } = router.query;
  const runId = Array.isArray(id) ? id[0] : id;
  const isReady = router.isReady;
  const [lifecycleState, setLifecycleState] = useState("");
  const missingRunError =
    isReady && !runId
      ? buildClientError({
          title: "Missing run id",
          summary: MISSING_RUN_ID_MESSAGE,
          actions: ["Open /runs/<id> with a valid run id."],
        })
      : null;

  const {
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
    signalMarkers,
    signalMarkersError,
    trades,
    tradesError,
    tradesPage,
    setTradesPage,
    tradesPageSize,
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
  } = useWorkspace(runId, { lifecycleState });

  const [activeTab, setActiveTab] = useState("strategy");
  const [selectedTrade, setSelectedTrade] = useState(null);
  const [rangeDraft, setRangeDraft] = useState({ start_ts: "", end_ts: "" });
  const [selectedStrategy, setSelectedStrategy] = useState("");
  const [strategyParams, setStrategyParams] = useState({});
  const [indicatorParams, setIndicatorParams] = useState({});
  const [chatModes, setChatModes] = useState(DEFAULT_CHAT_MODES);
  const [chatMode, setChatMode] = useState("add_indicator");
  const [chatContext, setChatContext] = useState({
    indicator_id: "",
    indicator_name: "",
    indicator_inputs: "close",
    indicator_outputs: "value",
    strategy_id: "",
    strategy_name: "",
    strategy_inputs: "close",
    strategy_indicators: "",
    plugin_kind: "indicator",
    plugin_id: "",
    error_text: "",
    run_id: "",
    trade_id: "",
    decision_id: "",
  });
  const [chatMessage, setChatMessage] = useState("");
  const [chatResponse, setChatResponse] = useState(null);
  const [chatError, setChatError] = useState(null);
  const [chatLoading, setChatLoading] = useState(false);
  const [errorMode, setErrorMode] = useState("simple");
  const [timelineFilters, setTimelineFilters] = useState({
    INFO: true,
    WARN: true,
    ERROR: true,
  });
  const [liveStatus, setLiveStatus] = useState(null);
  const [liveStatusError, setLiveStatusError] = useState(null);
  const [reportExporting, setReportExporting] = useState(false);
  const [reportExportError, setReportExportError] = useState(null);

  const rangeStart = range?.start_ts ?? "";
  const rangeEnd = range?.end_ts ?? "";

  useEffect(() => {
    setRangeDraft({ start_ts: rangeStart, end_ts: rangeEnd });
  }, [rangeStart, rangeEnd]);

  useEffect(() => {
    if (!runId) {
      setLifecycleState("");
      return;
    }
    if (!lifecycleState && run?.status) {
      setLifecycleState(String(run.status).toUpperCase());
    }
  }, [lifecycleState, run?.status, runId]);

  useEffect(() => {
    if (!runId) {
      return;
    }
    setChatContext((current) =>
      current.run_id ? current : { ...current, run_id: runId }
    );
  }, [runId]);

  useEffect(() => {
    let active = true;
    async function loadChatModes() {
      const result = await getChatModes();
      if (!active) {
        return;
      }
      if (result.ok && Array.isArray(result.data?.modes)) {
        const normalized = result.data.modes
          .map((mode) => ({
            id: mode.mode,
            label: mode.label || mode.mode,
            description: mode.description || "",
          }))
          .filter((mode) => mode.id);
        if (normalized.length > 0) {
          setChatModes(normalized);
          setChatMode((current) =>
            normalized.some((mode) => mode.id === current) ? current : normalized[0].id
          );
          return;
        }
      }
      setChatModes(DEFAULT_CHAT_MODES);
    }
    loadChatModes();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!runId) {
      setLiveStatus(null);
      setLiveStatusError(null);
      setLifecycleState("");
      return undefined;
    }
    let active = true;
    let timerId = null;
    let inFlight = false;

    const poll = async () => {
      if (!active || inFlight) {
        return;
      }
      inFlight = true;
      const result = await getRunStatus(runId, { bypassCache: true });
      inFlight = false;
      if (!active) {
        return;
      }
      if (!result.ok) {
        setLiveStatusError(mapApiErrorDetails(result, "Failed to load live status"));
        timerId = setTimeout(poll, 4000);
        return;
      }
      const statusPayload = result.data && typeof result.data === "object" ? result.data : null;
      setLiveStatus(statusPayload);
      setLiveStatusError(null);
      const state = String(statusPayload?.state || "").toUpperCase();
      if (state) {
        setLifecycleState(state);
      }
      if (!TERMINAL_RUN_STATES.has(state)) {
        timerId = setTimeout(poll, 2500);
      }
    };

    poll();
    return () => {
      active = false;
      inFlight = false;
      if (timerId) {
        clearTimeout(timerId);
      }
    };
  }, [runId]);

  const candles = useMemo(() => ohlcv?.candles || [], [ohlcv]);
  const chartMarkerSets = useMemo(() => {
    const sets = [];
    if (Array.isArray(markers) && markers.length > 0) {
      sets.push({
        runId: runId || "run",
        label: "Trades",
        markers,
        entryColor: "var(--accent)",
        exitColor: "var(--accent-2)",
        eventColor: "var(--accent-2)",
      });
    }
    if (Array.isArray(signalMarkers) && signalMarkers.length > 0) {
      sets.push({
        runId: `${runId || "run"}:signals`,
        label: "Signals",
        markers: signalMarkers,
        entryColor: "rgba(14, 122, 77, 0.95)",
        exitColor: "rgba(180, 35, 24, 0.95)",
        eventColor: "rgba(209, 147, 47, 0.95)",
      });
    }
    return sets;
  }, [markers, runId, signalMarkers]);
  const tradeRows = useMemo(() => trades?.results || [], [trades]);
  const demoMode = useMemo(
    () =>
      [run?.mode, summary?.mode, trades?.mode, metrics?.mode, timeline?.mode, ohlcv?.mode]
        .filter(Boolean)
        .some((mode) => mode === "demo"),
    [run?.mode, summary?.mode, trades?.mode, metrics?.mode, timeline?.mode, ohlcv?.mode]
  );
  const tradesTotal = Number.isFinite(trades?.total) ? trades.total : null;
  const tradesStart =
    tradeRows.length === 0 ? 0 : (tradesPage - 1) * tradesPageSize + 1;
  const tradesEnd =
    tradeRows.length === 0 ? 0 : tradesStart + tradeRows.length - 1;
  const tradesMaxPage =
    tradesTotal === null
      ? null
      : Math.max(1, Math.ceil(tradesTotal / tradesPageSize));
  const tradesCanPrev = tradesPage > 1;
  const tradesCanNext =
    tradesTotal === null ? tradeRows.length > 0 : tradesPage < tradesMaxPage;
  const timeBreakdown = useMemo(
    () => (Array.isArray(metrics?.time_breakdown) ? metrics.time_breakdown : []),
    [metrics]
  );
  const timeBreakdownColumns = useMemo(() => {
    if (!timeBreakdown.length) {
      return [];
    }
    const columns = [
      { key: "period", label: "Period" },
      { key: "total_return", label: "Total Return" },
      { key: "max_drawdown", label: "Max Drawdown" },
      { key: "win_rate", label: "Win Rate" },
      { key: "num_trades", label: "Trades" },
    ];
    return columns.filter((column) =>
      timeBreakdown.some((row) => {
        if (!row || typeof row !== "object") {
          return false;
        }
        const value = row[column.key];
        return value !== undefined && value !== null && value !== "";
      })
    );
  }, [timeBreakdown]);
  const filteredTimeline = useMemo(() => {
    if (!Array.isArray(timeline)) {
      return [];
    }
    return timeline
      .map((event, index) => ({
        event,
        index,
        severity: normalizeTimelineSeverity(event?.severity),
        dateKey: extractTimelineDate(event?.timestamp),
      }))
      .filter((item) => {
        if (item.severity?.alwaysVisible) {
          return true;
        }
        return timelineFilters[item.severity?.filterBucket] !== false;
      });
  }, [timeline, timelineFilters]);
  const timelineGroups = useMemo(() => {
    const groups = [];
    const indexByDate = new Map();
    filteredTimeline.forEach((item) => {
      if (!indexByDate.has(item.dateKey)) {
        indexByDate.set(item.dateKey, groups.length);
        groups.push({ dateKey: item.dateKey, items: [] });
      }
      groups[indexByDate.get(item.dateKey)].items.push(item);
    });
    return groups;
  }, [filteredTimeline]);
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
  const selectedStrategyMeta = useMemo(
    () => activeStrategies.find((item) => item.id === selectedStrategy) || null,
    [activeStrategies, selectedStrategy]
  );

  useEffect(() => {
    if (selectedStrategy || activeStrategies.length === 0) {
      return;
    }
    const runStrategy = run?.strategy;
    const match = activeStrategies.find((item) => item.id === runStrategy);
    setSelectedStrategy(match ? match.id : activeStrategies[0].id);
  }, [selectedStrategy, activeStrategies, run]);

  useEffect(() => {
    if (!selectedStrategy) {
      setStrategyParams({});
      return;
    }
    const selected = activeStrategies.find((item) => item.id === selectedStrategy);
    const defaults = buildParamDefaults(selected?.schema?.params);
    setStrategyParams(defaults);
  }, [selectedStrategy, activeStrategies]);

  useEffect(() => {
    if (!activeIndicators.length) {
      setIndicatorParams({});
      return;
    }
    setIndicatorParams((current) => {
      const next = { ...current };
      activeIndicators.forEach((indicator) => {
        if (!indicator || !indicator.id) {
          return;
        }
        if (!next[indicator.id]) {
          next[indicator.id] = buildParamDefaults(indicator?.schema?.params);
        }
      });
      return next;
    });
  }, [activeIndicators]);

  useEffect(() => {
    if (!selectedTrade) {
      return;
    }
    const selectedId = selectedTrade.trade_id || selectedTrade.id;
    const stillVisible = tradeRows.some((trade) => {
      const tradeId = trade.trade_id || trade.id;
      if (selectedId && tradeId) {
        return tradeId === selectedId;
      }
      return trade === selectedTrade;
    });
    if (!stillVisible) {
      setSelectedTrade(null);
    }
  }, [tradeRows, selectedTrade]);

  const applyRange = () => {
    setRange({
      start_ts: rangeDraft.start_ts,
      end_ts: rangeDraft.end_ts,
    });
  };

  const updateChatField = (field) => (event) => {
    const value = event.target.value;
    setChatContext((current) => ({ ...current, [field]: value }));
  };

  const submitChat = async () => {
    setChatLoading(true);
    setChatError(null);
    setChatResponse(null);

    const context = {};
    const setIf = (key, value) => {
      if (value === undefined || value === null || value === "") {
        return;
      }
      context[key] = value;
    };

    if (chatMode === "add_indicator") {
      setIf("indicator_id", chatContext.indicator_id);
      setIf("name", chatContext.indicator_name);
      setIf("inputs", parseCsv(chatContext.indicator_inputs));
      setIf("outputs", parseCsv(chatContext.indicator_outputs));
    }

    if (chatMode === "add_strategy") {
      setIf("strategy_id", chatContext.strategy_id);
      setIf("name", chatContext.strategy_name);
      setIf("inputs", parseCsv(chatContext.strategy_inputs));
      setIf("indicators", parseCsv(chatContext.strategy_indicators));
    }

    if (chatMode === "review_plugin") {
      setIf("kind", chatContext.plugin_kind);
      setIf("id", chatContext.plugin_id);
    }

    if (chatMode === "troubleshoot_errors") {
      setIf("error_text", chatContext.error_text || chatMessage);
      setIf("plugin_type", chatContext.plugin_kind);
      setIf("plugin_id", chatContext.plugin_id);
      setIf("run_id", chatContext.run_id || runId);
    }

    if (chatMode === "explain_trade") {
      setIf("run_id", chatContext.run_id || runId);
      setIf("trade_id", chatContext.trade_id);
      setIf("decision_id", chatContext.decision_id);
    }

    const payload = { mode: chatMode, message: chatMessage, context };

    const result = await postChat(payload);
    if (!result.ok) {
      setChatError(result.error || "Chat request failed.");
      setChatLoading(false);
      return;
    }
    setChatResponse(result.data);
    setChatLoading(false);
  };

  const riskPanelState = useMemo(
    () =>
      evaluateRiskPanelState({
        summary,
        summaryLoading,
        summaryError,
      }),
    [summary, summaryLoading, summaryError]
  );
  const risk = riskPanelState.risk;
  const riskStatusLabel = riskPanelState.statusLabel;
  const provenance = summary?.provenance || {};
  const provenanceStrategy =
    provenance?.strategy && typeof provenance.strategy === "object"
      ? provenance.strategy
      : {};
  const strategyHash = provenance.strategy_hash || provenanceStrategy.hash;
  const strategyId =
    provenance.strategy_id || provenanceStrategy.id || run?.strategy || "n/a";
  const strategyVersion =
    provenance.strategy_version || provenanceStrategy.version || "n/a";
  const riskLevel = provenance.risk_level ?? risk.level ?? "n/a";
  const riskConfigHash = provenance.risk_config_hash || "n/a";
  const runCreatedAt = provenance.run_created_at || run?.created_at || "n/a";
  const stageToken = provenance.stage_token || summary?.stage_token || "n/a";
  const liveState = String(
    liveStatus?.state || lifecycleState || run?.status || "UNKNOWN"
  ).toUpperCase();
  const livePercent = Number.isFinite(liveStatus?.percent) ? liveStatus.percent : 0;
  const liveLastEvent =
    liveStatus?.last_event && typeof liveStatus.last_event === "object"
      ? liveStatus.last_event
      : null;
  const liveEnvelope =
    liveStatus?.error_envelope && typeof liveStatus.error_envelope === "object"
      ? liveStatus.error_envelope
      : null;
  const liveRecoveryHint =
    typeof liveEnvelope?.recovery_hint === "string" ? liveEnvelope.recovery_hint : null;
  const liveHumanMessage =
    typeof liveEnvelope?.human_message === "string" ? liveEnvelope.human_message : null;
  const liveFailed = liveState === "FAILED" || liveState === "CORRUPTED";
  const artifactsPending = !artifactsReady;

  const updateStrategyParam = (name, value) => {
    setStrategyParams((current) => ({ ...current, [name]: value }));
  };

  const updateIndicatorParam = (indicatorId, name, value) => {
    setIndicatorParams((current) => ({
      ...current,
      [indicatorId]: { ...(current[indicatorId] || {}), [name]: value },
    }));
  };

  const renderParamInput = (param, value, onChange, options = {}) => {
    const { disabled = false, missingDefault = false } = options;
    const type = String(param?.type || "").toLowerCase();
    if (type === "bool") {
      return (
        <input
          type="checkbox"
          checked={value === true}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
        />
      );
    }
    if (type === "enum") {
      const enumOptions = Array.isArray(param.enum) ? param.enum : [];
      const selectValue = value ?? "";
      return (
        <select
          value={selectValue}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
        >
          {selectValue === "" && (
            <option value="">
              {missingDefault ? "Missing default" : "Select value"}
            </option>
          )}
          {enumOptions.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      );
    }
    if (type === "int" || type === "float") {
      const step = type === "int" ? 1 : 0.01;
      return (
        <input
          type="number"
          step={step}
          value={value ?? ""}
          min={param.min}
          max={param.max}
          disabled={disabled}
          placeholder={missingDefault ? "Missing default" : ""}
          onChange={(event) => onChange(event.target.value)}
        />
      );
    }
    return (
      <input
        type="text"
        value={value ?? ""}
        disabled={disabled}
        placeholder={missingDefault ? "Missing default" : ""}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  };

  const handleReportExport = async () => {
    if (!runId || reportExporting) {
      return;
    }
    setReportExporting(true);
    setReportExportError(null);
    const result = await exportRunReport(runId);
    if (!result.ok) {
      setReportExporting(false);
      setReportExportError(mapApiErrorDetails(result, "Report export failed"));
      return;
    }

    if (typeof window === "undefined") {
      setReportExporting(false);
      return;
    }
    const blob = result.data;
    const filename = result.filename || `${runId}-report.zip`;
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.URL.revokeObjectURL(url);
    setReportExporting(false);
  };

  return (
    <AppShell fullBleed>
      <main className="workspace-shell" data-testid="chart-workspace">
      <header className="workspace-header">
        <div>
          <div className="workspace-title">Chart Workspace</div>
          <div className="workspace-subtitle">
            Run <strong>{runId || "..."}</strong> - Read-only artifacts view
          </div>
        </div>
        <div className="workspace-actions">
          {demoMode && <span className="badge info">DEMO</span>}
          <label className="muted">
            Error mode
            <select
              value={errorMode}
              onChange={(event) => setErrorMode(event.target.value)}
              style={{ marginLeft: "8px" }}
            >
              <option value="simple">Simple</option>
              <option value="pro">Pro</option>
            </select>
          </label>
          <button
            className="secondary"
            onClick={handleReportExport}
            disabled={!runId || reportExporting}
          >
            {reportExporting ? "Exporting..." : "Export Report"}
          </button>
          <button className="secondary" onClick={reload}>
            Refresh
          </button>
        </div>
      </header>

      <section className="card fade-up" style={{ marginBottom: "16px" }}>
        <div className="section-title">
          <h3>Lifecycle Ribbon</h3>
          <span className={`badge ${runStateBadgeKind(liveState)}`}>{liveState}</span>
        </div>
        <div className="grid two">
          <div className="kpi">
            <span>Progress</span>
            <strong>{livePercent}%</strong>
          </div>
          <div className="kpi">
            <span>Artifact Surfaces</span>
            <strong>{artifactsPending ? "Locked" : "Ready"}</strong>
          </div>
          <div className="kpi">
            <span>Last Event</span>
            <strong>{liveLastEvent?.stage || "n/a"}</strong>
          </div>
          <div className="kpi">
            <span>Last Event Time</span>
            <strong>{liveLastEvent?.timestamp || "n/a"}</strong>
          </div>
        </div>
        <div className="muted" style={{ marginTop: "8px" }}>
          {lifecycleSummary(liveState)}
        </div>
      </section>

      {missingRunError && <ErrorNotice error={missingRunError} mode={errorMode} />}
      {demoMode && (
        <div className="banner info">
          Demo mode active. This run is loaded from ARTIFACTS_ROOT and is read-only.
        </div>
      )}
      {networkError && <ErrorNotice error={networkError} onRetry={reload} mode={errorMode} />}
      {transientRetryNotice && (
        <div className="banner info">
          <strong>{transientRetryNotice}</strong>
        </div>
      )}
      {pluginsError && <ErrorNotice error={pluginsError} onRetry={reload} mode={errorMode} />}
      {runError && <ErrorNotice error={runError} onRetry={reload} mode={errorMode} />}
      {summaryError && <ErrorNotice error={summaryError} onRetry={reload} mode={errorMode} />}
      {ohlcvError && (
        <ErrorNotice error={ohlcvError} onRetry={reload} compact mode={errorMode} />
      )}
      {markersError && (
        <ErrorNotice error={markersError} onRetry={reload} compact mode={errorMode} />
      )}
      {signalMarkersError && (
        <ErrorNotice error={signalMarkersError} onRetry={reload} compact mode={errorMode} />
      )}
      {reportExportError && (
        <ErrorNotice error={reportExportError} onRetry={handleReportExport} mode={errorMode} />
      )}

      <section className="workspace-meta">
        <div className="meta-card">
          <div className="meta-label">Status</div>
          <div className="meta-value">{liveState || "n/a"}</div>
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

      <section className="card fade-up" style={{ marginBottom: "16px" }}>
        <div className="section-title">
          <h3>Live Status</h3>
          <span className={`badge ${runStateBadgeKind(liveState)}`}>{liveState}</span>
        </div>
        {liveStatusError ? (
          <ErrorNotice error={liveStatusError} onRetry={reload} compact mode={errorMode} />
        ) : (
          <div className="grid two">
            <div className="kpi">
              <span>Progress</span>
              <strong>{livePercent}%</strong>
            </div>
            <div className="kpi">
              <span>Last Event</span>
              <strong>{liveLastEvent?.stage || "n/a"}</strong>
            </div>
            <div className="kpi">
              <span>Event Time</span>
              <strong>{liveLastEvent?.timestamp || "n/a"}</strong>
            </div>
            <div className="kpi">
              <span>Detail</span>
              <strong>{liveLastEvent?.detail || "n/a"}</strong>
            </div>
          </div>
        )}
        {liveFailed && (
          <div className="banner" style={{ marginTop: "12px", marginBottom: 0 }}>
            <strong>{liveHumanMessage || "Run failed."}</strong>
            {liveRecoveryHint && <div style={{ marginTop: "6px" }}>{liveRecoveryHint}</div>}
            {liveEnvelope && (
              <details style={{ marginTop: "8px" }}>
                <summary>Show details</summary>
                <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", marginTop: "6px" }}>
                  {JSON.stringify(liveEnvelope, null, 2)}
                </pre>
              </details>
            )}
          </div>
        )}
      </section>

      <div className="workspace-body">
        <section className="chart-panel">
          <div className="chart-toolbar">
            <label>
              Symbol
              <select
                value={symbol}
                onChange={(event) => setSymbol(event.target.value)}
                disabled={artifactsPending}
              >
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
                disabled={artifactsPending}
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
                disabled={artifactsPending}
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
                disabled={artifactsPending}
                onChange={(event) =>
                  setRangeDraft((current) => ({ ...current, end_ts: event.target.value }))
                }
              />
            </label>
            <button className="secondary" onClick={applyRange} disabled={artifactsPending}>
              Apply Range
            </button>
          </div>

          {artifactsPending ? (
            <div className="chart-empty" style={{ height: 420 }}>
              <p>Run is initializing. Chart artifacts load once lifecycle is RUNNING or terminal.</p>
              <div style={{ display: "grid", gap: "10px", width: "100%", maxWidth: "520px" }}>
                <div
                  style={{
                    height: "12px",
                    borderRadius: "999px",
                    background: "rgba(27, 32, 36, 0.12)",
                  }}
                />
                <div
                  style={{
                    height: "12px",
                    width: "88%",
                    borderRadius: "999px",
                    background: "rgba(27, 32, 36, 0.1)",
                  }}
                />
                <div
                  style={{
                    height: "12px",
                    width: "72%",
                    borderRadius: "999px",
                    background: "rgba(27, 32, 36, 0.08)",
                  }}
                />
              </div>
            </div>
          ) : ohlcvLoading ? (
            <div className="chart-empty" style={{ height: 420 }}>
              <p>Loading OHLCV artifacts...</p>
            </div>
          ) : (
            <CandlestickChart
              data={candles}
              markerSets={chartMarkerSets}
              enableDrawTools
              drawingScopeKey={runId || ""}
              height={420}
            />
          )}

          <div className="chart-status">
            <div>
              <span>Data range:</span>
              <strong>
                {artifactsPending
                  ? "waiting for lifecycle unlock"
                  : `${ohlcv?.start_ts ? ohlcv.start_ts : "n/a"} ->${
                      ohlcv?.end_ts ? ` ${ohlcv.end_ts}` : ""
                    }`}
              </strong>
            </div>
            <div>
              <span>Bars:</span> <strong>{artifactsPending ? "n/a" : ohlcv?.count ?? 0}</strong>
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
            {artifactsPending ? (
              <div className="panel-stack">
                <div className="panel-card">
                  <h3>Artifacts Initializing</h3>
                  <p className="muted">
                    Summary, trades, metrics, timeline, and diagnostics are deferred until the
                    run lifecycle reaches RUNNING or a terminal state.
                  </p>
                  <div style={{ display: "grid", gap: "10px", marginTop: "14px" }}>
                    <div
                      style={{
                        height: "12px",
                        borderRadius: "999px",
                        background: "rgba(27, 32, 36, 0.12)",
                      }}
                    />
                    <div
                      style={{
                        height: "12px",
                        width: "90%",
                        borderRadius: "999px",
                        background: "rgba(27, 32, 36, 0.1)",
                      }}
                    />
                    <div
                      style={{
                        height: "12px",
                        width: "80%",
                        borderRadius: "999px",
                        background: "rgba(27, 32, 36, 0.08)",
                      }}
                    />
                  </div>
                </div>
              </div>
            ) : (
              <>
            {activeTab === "strategy" && (
              <div className="panel-stack">
                <div className="panel-card">
                  <h3>Strategy Selection</h3>
                  {activeStrategies.length === 0 ? (
                    <p className="muted">
                      No active strategies found. Only validated (VALID) plugins are visible.
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
                  <h3>Strategy Parameters</h3>
                  {!selectedStrategyMeta?.schema ? (
                    <p className="muted">
                      Schema missing in validation artifacts. Re-run validation to hydrate.
                    </p>
                  ) : normalizeParams(selectedStrategyMeta.schema.params).length === 0 ? (
                    <p className="muted">No parameters declared for this strategy.</p>
                  ) : (
                    <div className="kv-grid">
                      {normalizeParams(selectedStrategyMeta.schema.params).map((param) => {
                        const missingDefault =
                          !hasParamDefault(param) || param.default === null;
                        return (
                          <div key={`${selectedStrategyMeta.id}-${param.name}`}>
                            <label
                              style={{ display: "flex", flexDirection: "column", gap: "4px" }}
                            >
                              <span>{param.name}</span>
                              {renderParamInput(
                                param,
                                strategyParams[param.name],
                                (value) => updateStrategyParam(param.name, value),
                                { disabled: missingDefault, missingDefault }
                              )}
                            </label>
                            {missingDefault && (
                              <span className="inline-warning" style={{ fontSize: "0.75rem" }}>
                                Missing default in schema. Re-run validation.
                              </span>
                            )}
                            {param.description && (
                              <span className="muted" style={{ fontSize: "0.75rem" }}>
                                {param.description}
                              </span>
                            )}
                          </div>
                        );
                      })}
                    </div>
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
                      <strong>{strategyVersion}</strong>
                    </div>
                    <div>
                      <span>Run ID</span>
                      <strong>{runId || "n/a"}</strong>
                    </div>
                  </div>
                </div>

                <div className="panel-card">
                  <h3>Risk Status</h3>
                  {riskPanelState.mode === "summary_unavailable" && (
                    <div className="banner info" style={{ marginBottom: "10px" }}>
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          gap: "10px",
                        }}
                      >
                        <div>
                          <strong>Summary unavailable.</strong>
                          <div className="muted">
                            {summaryLoading
                              ? "Loading summary artifacts."
                              : "Retry to refresh risk status."}
                          </div>
                        </div>
                        <button className="secondary" onClick={reload}>
                          Retry
                        </button>
                      </div>
                    </div>
                  )}
                  {riskPanelState.mode === "unknown" && (
                    <div className="banner info" style={{ marginBottom: "10px" }}>
                      <strong>Risk status is UNKNOWN.</strong>
                      <div className="muted">
                        Summary loaded, but risk status is missing from artifacts.
                      </div>
                    </div>
                  )}
                  {riskPanelState.mode === "warning" && (
                    <div className="inline-warning">
                      Risk artifacts missing or incomplete (status: {riskStatusLabel}). UI is
                      fail-closed.
                    </div>
                  )}
                  <div className="kv-grid">
                    <div>
                      <span>Risk Level</span>
                      <strong>{riskLevel}</strong>
                    </div>
                    <div>
                      <span>Status</span>
                      <strong>{riskStatusLabel}</strong>
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
                      <span>Strategy ID</span>
                      <strong>{strategyId}</strong>
                    </div>
                    <div>
                      <span>Strategy Hash</span>
                      <strong>{strategyHash || "n/a"}</strong>
                    </div>
                    <div>
                      <span>Risk Config Hash</span>
                      <strong>{riskConfigHash}</strong>
                    </div>
                    <div>
                      <span>Run Created At</span>
                      <strong>{runCreatedAt}</strong>
                    </div>
                    <div>
                      <span>Stage Token</span>
                      <strong>{stageToken}</strong>
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
                </div>
              </div>
            )}

            {activeTab === "indicators" && (
              <div className="panel-stack">
                <div className="panel-card">
                  <h3>Indicators</h3>
                  {activeIndicators.length === 0 && (
                    <p className="muted">
                      No active indicators found. Only validated (VALID) plugins are visible.
                    </p>
                  )}
                </div>
                {activeIndicators.map((indicator) => (
                  <div key={indicator.id} className="panel-card">
                    <h4>
                      {indicator.name ? `${indicator.name} (${indicator.id})` : indicator.id}
                    </h4>
                    <p className="muted">
                      Version: {indicator.version || "n/a"} | Warmup:{" "}
                      {indicator.schema?.warmup_bars ?? "n/a"} | NaN policy:{" "}
                      {indicator.schema?.nan_policy || "n/a"}
                    </p>
                    {!indicator.schema ? (
                      <p className="muted">
                        Schema missing in validation artifacts. Re-run validation to hydrate.
                      </p>
                    ) : normalizeParams(indicator.schema.params).length === 0 ? (
                      <p className="muted">No parameters declared for this indicator.</p>
                    ) : (
                      <div className="kv-grid">
                        {normalizeParams(indicator.schema.params).map((param) => {
                          const missingDefault =
                            !hasParamDefault(param) || param.default === null;
                          return (
                            <div key={`${indicator.id}-${param.name}`}>
                              <label
                                style={{ display: "flex", flexDirection: "column", gap: "4px" }}
                              >
                                <span>{param.name}</span>
                                {renderParamInput(
                                  param,
                                  indicatorParams[indicator.id]?.[param.name],
                                  (value) =>
                                    updateIndicatorParam(indicator.id, param.name, value),
                                  { disabled: missingDefault, missingDefault }
                                )}
                              </label>
                              {missingDefault && (
                                <span className="inline-warning" style={{ fontSize: "0.75rem" }}>
                                  Missing default in schema. Re-run validation.
                                </span>
                              )}
                              {param.description && (
                                <span className="muted" style={{ fontSize: "0.75rem" }}>
                                  {param.description}
                                </span>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {activeTab === "trades" && (
              <div className="panel-stack">
                {tradesError ? (
                  <div className="panel-card">
                    <h3>Trades</h3>
                    <ErrorNotice
                      error={tradesError}
                      onRetry={reload}
                      compact
                      mode={errorMode}
                    />
                  </div>
                ) : (
                  <>
                    <div className="panel-card">
                      <h3>Trades</h3>
                      <div
                        className="chart-toolbar"
                        style={{ justifyContent: "space-between", marginBottom: "8px" }}
                      >
                        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                          <button
                            className="secondary"
                            disabled={!tradesCanPrev}
                            onClick={() =>
                              setTradesPage((value) => Math.max(1, value - 1))
                            }
                          >
                            Prev
                          </button>
                          <span className="muted" style={{ fontSize: "0.8rem" }}>
                            Page {tradesPage}
                            {tradesMaxPage ? ` of ${tradesMaxPage}` : ""}
                          </span>
                          <button
                            className="secondary"
                            disabled={!tradesCanNext}
                            onClick={() =>
                              setTradesPage((value) =>
                                tradesMaxPage ? Math.min(tradesMaxPage, value + 1) : value + 1
                              )
                            }
                          >
                            Next
                          </button>
                        </div>
                        <label>
                          Page size
                          <select
                            value={tradesPageSize}
                            onChange={(event) =>
                              setTradesPageSize(Number(event.target.value))
                            }
                          >
                            {TRADE_PAGE_SIZES.map((size) => (
                              <option key={size} value={size}>
                                {size}
                              </option>
                            ))}
                          </select>
                        </label>
                        {tradesTotal !== null && (
                          <div className="muted" style={{ fontSize: "0.8rem" }}>
                            Showing {tradesStart}–{tradesEnd} of {tradesTotal}
                          </div>
                        )}
                      </div>
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
                            <strong>{strategyVersion}</strong>
                          </div>
                          <div>
                            <span>Data Snapshot Hash</span>
                            <strong>{provenance.data_snapshot_hash || "n/a"}</strong>
                          </div>
                          <div>
                            <span>Feature Snapshot Hash</span>
                            <strong>{provenance.feature_snapshot_hash || "n/a"}</strong>
                          </div>
                          <div>
                            <span>Stage Token</span>
                            <strong>{stageToken}</strong>
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
                  <ErrorNotice
                    error={metricsError}
                    onRetry={reload}
                    compact
                    mode={errorMode}
                  />
                ) : metrics ? (
                  <>
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
                    <div style={{ marginTop: "16px" }}>
                      <h4 style={{ margin: "0 0 8px 0" }}>Time Breakdown</h4>
                      {timeBreakdown.length > 0 && timeBreakdownColumns.length > 0 ? (
                        <div className="table-wrap">
                          <table>
                            <thead>
                              <tr>
                                {timeBreakdownColumns.map((column) => (
                                  <th key={column.key}>{column.label}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {timeBreakdown.map((row, index) => (
                                <tr key={`breakdown-${index}`}>
                                  {timeBreakdownColumns.map((column) => (
                                    <td key={`${column.key}-${index}`}>
                                      {formatMetricValue(row?.[column.key])}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <p className="muted">Time breakdown not available.</p>
                      )}
                    </div>
                  </>
                ) : (
                  <p className="muted">Metrics artifact not available.</p>
                )}
              </div>
            )}

            {activeTab === "timeline" && (
              <div className="panel-card">
                <h3>Timeline</h3>
                {timelineError ? (
                  <ErrorNotice
                    error={timelineError}
                    onRetry={reload}
                    compact
                    mode={errorMode}
                  />
                ) : (
                  <div className="timeline-list">
                    <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
                      {["INFO", "WARN", "ERROR"].map((level) => (
                        <label
                          key={level}
                          className="muted"
                          style={{ display: "flex", gap: "6px", alignItems: "center" }}
                        >
                          <input
                            type="checkbox"
                            checked={timelineFilters[level]}
                            onChange={(event) =>
                              setTimelineFilters((current) => ({
                                ...current,
                                [level]: event.target.checked,
                              }))
                            }
                          />
                          {level}
                        </label>
                      ))}
                    </div>
                    {timeline.length === 0 ? (
                      <p className="muted">No timeline events found in artifacts.</p>
                    ) : filteredTimeline.length === 0 ? (
                      <p className="muted">No timeline events match the selected severities.</p>
                    ) : (
                      timelineGroups.map((group) => (
                      <div key={`timeline-${group.dateKey}`}>
                        <h4 style={{ margin: "12px 0 6px 0" }}>{group.dateKey}</h4>
                        {group.items.map((item) => {
                          const event = item.event || {};
                          return (
                            <div
                              key={`${event.timestamp}-${item.index}`}
                              className="timeline-item"
                            >
                              <div className="timeline-time">{event.timestamp}</div>
                              <div>
                                <strong>{event.title || event.type}</strong>
                                {event.detail && <p className="muted">{event.detail}</p>}
                                <span className="pill">{item.severity?.label || "INFO"}</span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                      ))
                    )}
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
              <div className="panel-stack">
                <div className="panel-card">
                  <h3>AI Chat</h3>
                  <p className="muted">
                    Read-only guide and reviewer. Generates templates and explains artifacts
                    without executing trades.
                  </p>
                  <div className="chat-wizard">
                    <div className="chat-fields">
                      <label>
                        Mode
                        <select
                          value={chatMode}
                          onChange={(event) => setChatMode(event.target.value)}
                        >
                          {chatModes.map((mode) => (
                            <option key={mode.id} value={mode.id}>
                              {mode.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      {chatModes.find((mode) => mode.id === chatMode)?.description && (
                        <p className="muted">
                          {chatModes.find((mode) => mode.id === chatMode).description}
                        </p>
                      )}
                    </div>

                    {chatMode === "add_indicator" && (
                      <div className="chat-fields">
                        <label>
                          Indicator ID
                          <input
                            type="text"
                            value={chatContext.indicator_id}
                            onChange={updateChatField("indicator_id")}
                            placeholder="simple_rsi"
                          />
                        </label>
                        <label>
                          Name
                          <input
                            type="text"
                            value={chatContext.indicator_name}
                            onChange={updateChatField("indicator_name")}
                            placeholder="Simple RSI"
                          />
                        </label>
                        <label>
                          Inputs (comma-separated)
                          <input
                            type="text"
                            value={chatContext.indicator_inputs}
                            onChange={updateChatField("indicator_inputs")}
                          />
                        </label>
                        <label>
                          Outputs (comma-separated)
                          <input
                            type="text"
                            value={chatContext.indicator_outputs}
                            onChange={updateChatField("indicator_outputs")}
                          />
                        </label>
                      </div>
                    )}

                    {chatMode === "add_strategy" && (
                      <div className="chat-fields">
                        <label>
                          Strategy ID
                          <input
                            type="text"
                            value={chatContext.strategy_id}
                            onChange={updateChatField("strategy_id")}
                            placeholder="simple_cross"
                          />
                        </label>
                        <label>
                          Name
                          <input
                            type="text"
                            value={chatContext.strategy_name}
                            onChange={updateChatField("strategy_name")}
                            placeholder="Simple Cross"
                          />
                        </label>
                        <label>
                          Series Inputs (comma-separated)
                          <input
                            type="text"
                            value={chatContext.strategy_inputs}
                            onChange={updateChatField("strategy_inputs")}
                          />
                        </label>
                        <label>
                          Required Indicators (comma-separated)
                          <input
                            type="text"
                            value={chatContext.strategy_indicators}
                            onChange={updateChatField("strategy_indicators")}
                            placeholder="rsi, ema_fast"
                          />
                        </label>
                      </div>
                    )}

                    {chatMode === "review_plugin" && (
                      <div className="chat-fields">
                        <label>
                          Plugin Type
                          <select
                            value={chatContext.plugin_kind}
                            onChange={updateChatField("plugin_kind")}
                          >
                            <option value="indicator">Indicator</option>
                            <option value="strategy">Strategy</option>
                          </select>
                        </label>
                        <label>
                          Plugin ID
                          <input
                            type="text"
                            value={chatContext.plugin_id}
                            onChange={updateChatField("plugin_id")}
                            placeholder="simple_rsi"
                          />
                        </label>
                      </div>
                    )}

                    {chatMode === "troubleshoot_errors" && (
                      <div className="chat-fields">
                        <label>
                          Error Text
                          <textarea
                            value={chatContext.error_text}
                            onChange={updateChatField("error_text")}
                            placeholder="Paste validation errors or traceback here."
                            rows={4}
                          />
                        </label>
                        <label>
                          Plugin Type (optional)
                          <select
                            value={chatContext.plugin_kind}
                            onChange={updateChatField("plugin_kind")}
                          >
                            <option value="indicator">Indicator</option>
                            <option value="strategy">Strategy</option>
                          </select>
                        </label>
                        <label>
                          Plugin ID (optional)
                          <input
                            type="text"
                            value={chatContext.plugin_id}
                            onChange={updateChatField("plugin_id")}
                            placeholder="simple_rsi"
                          />
                        </label>
                        <label>
                          Run ID (optional)
                          <input
                            type="text"
                            value={chatContext.run_id}
                            onChange={updateChatField("run_id")}
                            placeholder={runId || "run-123"}
                          />
                        </label>
                      </div>
                    )}

                    {chatMode === "explain_trade" && (
                      <div className="chat-fields">
                        <label>
                          Run ID
                          <input
                            type="text"
                            value={chatContext.run_id}
                            onChange={updateChatField("run_id")}
                            placeholder={runId || "run-123"}
                          />
                        </label>
                        <label>
                          Trade ID
                          <input
                            type="text"
                            value={chatContext.trade_id}
                            onChange={updateChatField("trade_id")}
                            placeholder="trade-001"
                          />
                        </label>
                        <label>
                          Decision ID (optional)
                          <input
                            type="text"
                            value={chatContext.decision_id}
                            onChange={updateChatField("decision_id")}
                            placeholder="decision-001"
                          />
                        </label>
                      </div>
                    )}

                    <div className="chat-fields">
                      <label>
                        Message
                        <textarea
                          value={chatMessage}
                          onChange={(event) => setChatMessage(event.target.value)}
                          placeholder="Describe what you want to build or review."
                          rows={3}
                        />
                      </label>
                    </div>

                    <div className="chat-actions">
                      <button onClick={submitChat} disabled={chatLoading}>
                        {chatLoading ? "Generating..." : "Generate Guide"}
                      </button>
                      <span className="muted">No execution is triggered from this panel.</span>
                    </div>
                  </div>
                </div>

                <div className="panel-card">
                  <h3>Response</h3>
                  {chatError && <p className="inline-warning">{chatError}</p>}
                  {!chatError && !chatResponse && (
                    <p className="muted">No response yet. Submit a request above.</p>
                  )}
                  {chatResponse && (
                    <div className="chat-response">
                      <div className="chat-section">
                        <h4>{chatResponse.title || "Response"}</h4>
                        {chatResponse.summary && (
                          <p className="muted">{chatResponse.summary}</p>
                        )}
                        {chatResponse.blockers?.length > 0 && (
                          <div className="chat-alert chat-alert-danger">
                            <strong>Blockers</strong>
                            <ul className="chat-list">
                              {chatResponse.blockers.map((item, index) => (
                                <li key={`blocker-${index}`}>{item}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {chatResponse.warnings?.length > 0 && (
                          <div className="chat-alert chat-alert-warning">
                            <strong>Warnings</strong>
                            <ul className="chat-list">
                              {chatResponse.warnings.map((item, index) => (
                                <li key={`warning-${index}`}>{item}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>

                      <div className="chat-section">
                        <h4>Steps</h4>
                        {chatResponse.steps?.length ? (
                          <ul className="chat-list">
                            {chatResponse.steps.map((item, index) => (
                              <li key={item.id || `step-${index}`}>{item.text || item}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="muted">No steps returned.</p>
                        )}
                      </div>

                      <div className="chat-section">
                        <h4>Files To Create</h4>
                        {chatResponse.files_to_create?.length ? (
                          <div className="chat-file-list">
                            {chatResponse.files_to_create.map((file, index) => (
                              <details key={`file-${index}`} className="chat-file">
                                <summary className="chat-file-path">{file.path}</summary>
                                <pre className="chat-code">{file.contents}</pre>
                              </details>
                            ))}
                          </div>
                        ) : (
                          <p className="muted">No files for this response.</p>
                        )}
                      </div>

                      <div className="chat-section">
                        <h4>Commands</h4>
                        {chatResponse.commands?.length ? (
                          <ul className="chat-list">
                            {chatResponse.commands.map((item, index) => (
                              <li key={`cmd-${index}`}>
                                <code>{item}</code>
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <p className="muted">No commands returned.</p>
                        )}
                      </div>

                      <div className="chat-section">
                        <h4>Success Criteria</h4>
                        {chatResponse.success_criteria?.length ? (
                          <ul className="chat-list">
                            {chatResponse.success_criteria.map((item, index) => (
                              <li key={`success-${index}`}>{item}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="muted">No success criteria returned.</p>
                        )}
                      </div>
                      {chatResponse.review && (
                        <div className="chat-section">
                          <h4>Review Summary</h4>
                          <div className="chat-alert chat-alert-danger">
                            <strong>Issues</strong>
                            {chatResponse.review.issues?.length ? (
                              <ul className="chat-list">
                                {chatResponse.review.issues.map((item, index) => (
                                  <li key={`review-issue-${index}`}>{item}</li>
                                ))}
                              </ul>
                            ) : (
                              <p className="muted">No issues reported.</p>
                            )}
                          </div>
                          <div className="chat-alert chat-alert-warning">
                            <strong>Warnings</strong>
                            {chatResponse.review.warnings?.length ? (
                              <ul className="chat-list">
                                {chatResponse.review.warnings.map((item, index) => (
                                  <li key={`review-warning-${index}`}>{item}</li>
                                ))}
                              </ul>
                            ) : (
                              <p className="muted">No warnings reported.</p>
                            )}
                          </div>
                          <div className="chat-section">
                            <h4>Suggestions</h4>
                            {chatResponse.review.suggestions?.length ? (
                              <ul className="chat-list">
                                {chatResponse.review.suggestions.map((item, index) => (
                                  <li key={`review-suggestion-${index}`}>{item}</li>
                                ))}
                              </ul>
                            ) : (
                              <p className="muted">No suggestions returned.</p>
                            )}
                          </div>
                          <div className="chat-section">
                            <h4>Next Tests</h4>
                            {chatResponse.review.next_tests?.length ? (
                              <ul className="chat-list">
                                {chatResponse.review.next_tests.map((item, index) => (
                                  <li key={`review-test-${index}`}>
                                    <code>{item}</code>
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <p className="muted">No next tests returned.</p>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
              </>
            )}
          </div>
        </aside>
      </div>
      </main>
    </AppShell>
  );
}

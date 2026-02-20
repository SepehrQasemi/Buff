const FALLBACK_TIMEFRAME = "1m";

const normalizeTimeframe = (value) => {
  const text = String(value || "").trim();
  return text || null;
};

const normalizeList = (values) => {
  if (!Array.isArray(values)) {
    return [];
  }
  const seen = new Set();
  const normalized = [];
  for (const value of values) {
    const timeframe = normalizeTimeframe(value);
    if (!timeframe || seen.has(timeframe)) {
      continue;
    }
    seen.add(timeframe);
    normalized.push(timeframe);
  }
  return normalized;
};

export const deriveAvailableTimeframes = (summary, runTimeframe) => {
  const fromSummary = normalizeList(summary?.ohlcv_available_timeframes);
  if (fromSummary.length > 0) {
    return fromSummary;
  }
  const runDefault = normalizeTimeframe(runTimeframe);
  if (runDefault) {
    return [runDefault];
  }
  return [FALLBACK_TIMEFRAME];
};

export const pickPreferredTimeframe = ({
  currentTimeframe,
  runTimeframe,
  availableTimeframes,
}) => {
  const available = normalizeList(availableTimeframes);
  if (available.length === 0) {
    return FALLBACK_TIMEFRAME;
  }
  const current = normalizeTimeframe(currentTimeframe);
  if (current && available.includes(current)) {
    return current;
  }
  const runDefault = normalizeTimeframe(runTimeframe);
  if (runDefault && available.includes(runDefault)) {
    return runDefault;
  }
  return available[0];
};

export const buildOhlcvUnavailableMessage = (timeframe, availableTimeframes) => {
  const requested = normalizeTimeframe(timeframe) || "unknown";
  const available = normalizeList(availableTimeframes);
  const availableLabel = available.length > 0 ? available.join(", ") : "none";
  return `No OHLCV for timeframe ${requested}. Available: ${availableLabel}.`;
};

export const evaluateRiskPanelState = ({ summary, summaryLoading, summaryError }) => {
  const summaryReady = Boolean(summary) && !summaryLoading && !summaryError;
  if (!summaryReady) {
    return {
      mode: "summary_unavailable",
      statusLabel: "UNKNOWN",
      risk: {},
    };
  }

  const risk = summary?.risk && typeof summary.risk === "object" ? summary.risk : {};
  const rawStatus = typeof risk.status === "string" ? risk.status.trim() : "";
  if (!rawStatus) {
    return {
      mode: "unknown",
      statusLabel: "UNKNOWN",
      risk,
    };
  }

  const normalizedStatus = rawStatus.toLowerCase();
  if (
    normalizedStatus === "unknown" ||
    normalizedStatus === "n/a" ||
    normalizedStatus === "na"
  ) {
    return {
      mode: "unknown",
      statusLabel: "UNKNOWN",
      risk,
    };
  }
  if (normalizedStatus !== "ok") {
    return {
      mode: "warning",
      statusLabel: rawStatus.toUpperCase(),
      risk,
    };
  }

  return {
    mode: "ok",
    statusLabel: "OK",
    risk,
  };
};

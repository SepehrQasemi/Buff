const DEFAULT_PAGE_SIZE = 25;
const MAX_PAGE_SIZE = 500;
const DEFAULT_TAB = "decisions";

const toStringValue = (value) => {
  if (Array.isArray(value)) {
    return value.filter(Boolean).join(",");
  }
  if (value === undefined || value === null) {
    return "";
  }
  return String(value);
};

const normalizeCsvList = (value) => {
  if (!value) {
    return "";
  }
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .join(",");
};

const normalizeNumber = (value, fallback, min, max) => {
  const parsed = Number.parseInt(value, 10);
  if (Number.isNaN(parsed)) {
    return fallback;
  }
  if (parsed < min) {
    return min;
  }
  if (max !== undefined && parsed > max) {
    return max;
  }
  return parsed;
};

export const normalizeTimestampForUrl = (value) => {
  if (!value) {
    return "";
  }
  const raw = String(value).trim();
  if (!raw) {
    return "";
  }
  const numeric = /^\d+$/.test(raw);
  const date = numeric ? new Date(Number(raw)) : new Date(raw);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toISOString();
};

export const parseViewState = (query) => {
  const symbol = normalizeCsvList(toStringValue(query.symbol));
  const action = normalizeCsvList(toStringValue(query.action));
  const severity = normalizeCsvList(toStringValue(query.severity));
  const reason_code = normalizeCsvList(toStringValue(query.reason_code));

  const start_ts = normalizeTimestampForUrl(toStringValue(query.start_ts));
  const end_ts = normalizeTimestampForUrl(toStringValue(query.end_ts));

  const page = normalizeNumber(toStringValue(query.page), 1, 1);
  const page_size = normalizeNumber(
    toStringValue(query.page_size),
    DEFAULT_PAGE_SIZE,
    1,
    MAX_PAGE_SIZE
  );

  const active_tab = toStringValue(query.tab || query.active_tab) || DEFAULT_TAB;

  return {
    symbol,
    action,
    severity,
    reason_code,
    start_ts,
    end_ts,
    page,
    page_size,
    active_tab,
  };
};

export const serializeViewState = (state) => {
  const query = {};
  if (state.symbol) query.symbol = state.symbol;
  if (state.action) query.action = state.action;
  if (state.severity) query.severity = state.severity;
  if (state.reason_code) query.reason_code = state.reason_code;

  const start = normalizeTimestampForUrl(state.start_ts);
  const end = normalizeTimestampForUrl(state.end_ts);
  if (start) query.start_ts = start;
  if (end) query.end_ts = end;

  if (state.page && state.page !== 1) query.page = String(state.page);
  if (state.page_size && state.page_size !== DEFAULT_PAGE_SIZE) {
    query.page_size = String(state.page_size);
  }
  if (state.active_tab && state.active_tab !== DEFAULT_TAB) {
    query.tab = state.active_tab;
  }

  return query;
};

export const buildQueryString = (query) => new URLSearchParams(query).toString();

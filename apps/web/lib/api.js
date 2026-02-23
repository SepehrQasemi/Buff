const DEFAULT_API_BASE = "http://127.0.0.1:8000";
const API_VERSION_PATH = "/api/v1";
const CACHE_MAX_ENTRIES = 50;
const DEFAULT_BUFF_USER = "phase1_smoke_user";

class LruCache {
  constructor(maxEntries) {
    this.maxEntries = maxEntries;
    this.entries = new Map();
  }

  get(key) {
    if (!this.entries.has(key)) {
      return null;
    }
    const value = this.entries.get(key);
    this.entries.delete(key);
    this.entries.set(key, value);
    return value;
  }

  set(key, value) {
    if (this.entries.has(key)) {
      this.entries.delete(key);
    }
    this.entries.set(key, value);
    while (this.entries.size > this.maxEntries) {
      const oldestKey = this.entries.keys().next().value;
      this.entries.delete(oldestKey);
    }
  }

  delete(key) {
    this.entries.delete(key);
  }

  clear() {
    this.entries.clear();
  }

  keys() {
    return this.entries.keys();
  }
}

const REQUEST_CACHE = new LruCache(CACHE_MAX_ENTRIES);

const getRuntimeBase = () => {
  if (typeof window === "undefined") {
    return null;
  }
  if (window.__RUNTIME_CONFIG__ && typeof window.__RUNTIME_CONFIG__.API_BASE === "string") {
    return window.__RUNTIME_CONFIG__.API_BASE;
  }
  if (typeof window.__BUFF_API_BASE__ === "string") {
    return window.__BUFF_API_BASE__;
  }
  return null;
};

const normalizeBase = (base) => {
  if (!base) {
    return `${DEFAULT_API_BASE}${API_VERSION_PATH}/`;
  }
  const trimmed = String(base).trim().replace(/\/+$/, "");
  const hasApiVersion = /\/api\/v1(\/|$)/.test(trimmed);
  const withVersion = hasApiVersion ? trimmed : `${trimmed}${API_VERSION_PATH}`;
  return `${withVersion}/`;
};

const API_BASE = normalizeBase(
  getRuntimeBase() || process.env.NEXT_PUBLIC_API_BASE || DEFAULT_API_BASE
);

const buildQuery = (params = {}) => {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") {
      return;
    }
    if (Array.isArray(value)) {
      value.forEach((item) => query.append(key, item));
      return;
    }
    query.set(key, value);
  });
  return query.toString();
};

const buildStableQuery = (params = {}) => {
  const query = new URLSearchParams();
  Object.keys(params)
    .sort()
    .forEach((key) => {
      const value = params[key];
      if (value === undefined || value === null || value === "") {
        return;
      }
      if (Array.isArray(value)) {
        value.forEach((item) => query.append(key, item));
        return;
      }
      query.append(key, value);
    });
  return query.toString();
};

const buildCacheKey = (path, params) => {
  const normalizedPath = String(path || "").replace(/^\/+/, "");
  const query = buildStableQuery(params);
  return `${API_BASE}${normalizedPath}${query ? `?${query}` : ""}`;
};

const normalizeUserValue = (value) => {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed || null;
};

const resolveBuffUser = () => {
  if (typeof window !== "undefined") {
    const runtimeUser = normalizeUserValue(window.__RUNTIME_CONFIG__?.BUFF_USER);
    if (runtimeUser) {
      return runtimeUser;
    }
    const legacyRuntimeUser = normalizeUserValue(window.__BUFF_USER__);
    if (legacyRuntimeUser) {
      return legacyRuntimeUser;
    }
  }
  return (
    normalizeUserValue(process.env.UI_SMOKE_USER) ||
    normalizeUserValue(process.env.BUFF_USER) ||
    normalizeUserValue(process.env.NEXT_PUBLIC_BUFF_USER) ||
    DEFAULT_BUFF_USER
  );
};

const withUserHeader = (headers = {}) => ({
  ...(headers || {}),
  "X-Buff-User": resolveBuffUser(),
});

export const invalidateCache = ({ runId, prefixes } = {}) => {
  const needles = [];
  if (runId) {
    needles.push(`/runs/${runId}`);
  }
  if (Array.isArray(prefixes)) {
    needles.push(...prefixes.filter(Boolean));
  }
  if (needles.length === 0) {
    REQUEST_CACHE.clear();
    return;
  }
  for (const key of REQUEST_CACHE.keys()) {
    if (needles.some((needle) => key.includes(needle))) {
      REQUEST_CACHE.delete(key);
    }
  }
};

const parseErrorMessage = (data, fallback) => {
  if (!data) {
    return fallback;
  }
  if (typeof data === "string") {
    return data;
  }
  if (typeof data.message === "string") {
    return data.message;
  }
  if (typeof data.detail === "string") {
    return data.detail;
  }
  if (typeof data.detail?.message === "string") {
    return data.detail.message;
  }
  if (typeof data.error === "string") {
    return data.error;
  }
  if (typeof data.error?.message === "string") {
    return data.error.message;
  }
  return fallback;
};

const parseResponseData = async (response) => {
  const contentType = response.headers.get("content-type") || "";
  const isJson = contentType.includes("json");
  if (isJson) {
    return { data: await response.json(), isJson: true };
  }
  return { data: await response.text(), isJson: false };
};

const parseContentDispositionFilename = (value) => {
  if (!value || typeof value !== "string") {
    return null;
  }
  const utf8Match = value.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match && utf8Match[1]) {
    try {
      return decodeURIComponent(utf8Match[1].replace(/["']/g, ""));
    } catch {
      return utf8Match[1].replace(/["']/g, "");
    }
  }
  const match = value.match(/filename="?([^";]+)"?/i);
  if (!match || !match[1]) {
    return null;
  }
  return match[1];
};

const extractCanonicalErrorInfo = (payload) => {
  if (!payload || typeof payload !== "object") {
    return { code: null, message: null, details: null, envelope: null };
  }

  const envelope =
    payload.error_envelope ||
    payload.error?.envelope ||
    payload.error?.error_envelope ||
    payload.detail?.error_envelope ||
    payload.details?.error_envelope ||
    payload.error?.details?.error_envelope ||
    null;

  if (payload.error && typeof payload.error === "object") {
    return {
      code: payload.error.code || null,
      message: payload.error.message || null,
      details: payload.error.details || null,
      envelope,
    };
  }

  if (payload.detail && typeof payload.detail === "object") {
    return {
      code: payload.detail.code || null,
      message: payload.detail.message || null,
      details: payload.detail.details || null,
      envelope,
    };
  }

  return {
    code: payload.code || null,
    message: payload.message || null,
    details: payload.details || null,
    envelope,
  };
};

const withCanonicalErrorInfo = (result) => {
  if (!result || result.ok || !result.status) {
    return result;
  }
  return {
    ...result,
    ...extractCanonicalErrorInfo(result.data),
  };
};

export const buildApiUrl = (path, params) => {
  const normalizedPath = String(path || "").replace(/^\/+/, "");
  const url = new URL(normalizedPath, API_BASE);
  const query = buildQuery(params);
  if (query) {
    url.search = query;
  }
  return url.toString();
};

const request = async (path, params, options = {}) => {
  const { signal, cache = false, bypassCache = false, headers } = options;
  const cacheKey = cache ? buildCacheKey(path, params) : null;

  if (cache && !bypassCache && cacheKey) {
    const cached = REQUEST_CACHE.get(cacheKey);
    if (cached) {
      return { ok: true, status: 200, data: cached.data, cached: true };
    }
  }

  const url = buildApiUrl(path, params);

  try {
    const response = await fetch(url, { signal, headers });
    const { data, isJson } = await parseResponseData(response);

    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        error: parseErrorMessage(data, `Request failed (${response.status})`),
        data,
      };
    }

    if (cache && cacheKey && isJson) {
      REQUEST_CACHE.set(cacheKey, { data });
    }
    return { ok: true, status: response.status, data };
  } catch (error) {
    if (error?.name === "AbortError") {
      return { ok: false, aborted: true };
    }
    return { ok: false, error: error?.message || "Network error" };
  }
};

const post = async (path, payload, options = {}) => {
  const { headers } = options;
  const url = buildApiUrl(path);
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(headers || {}),
      },
      body: JSON.stringify(payload || {}),
    });
    const { data } = await parseResponseData(response);
    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        error: parseErrorMessage(data, `Request failed (${response.status})`),
        data,
      };
    }
    return { ok: true, status: response.status, data };
  } catch (error) {
    return { ok: false, error: error?.message || "Network error" };
  }
};

const postForm = async (path, formData, options = {}) => {
  const { headers } = options;
  const url = buildApiUrl(path);
  try {
    const response = await fetch(url, {
      method: "POST",
      headers,
      body: formData,
    });
    const { data } = await parseResponseData(response);
    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        error: parseErrorMessage(data, `Request failed (${response.status})`),
        data,
      };
    }
    return { ok: true, status: response.status, data };
  } catch (error) {
    return { ok: false, error: error?.message || "Network error" };
  }
};

const requestBlob = async (path, options = {}) => {
  const { headers } = options;
  const url = buildApiUrl(path);
  try {
    const response = await fetch(url, { headers });
    if (!response.ok) {
      const { data } = await parseResponseData(response);
      return {
        ok: false,
        status: response.status,
        error: parseErrorMessage(data, `Request failed (${response.status})`),
        data,
      };
    }
    const blob = await response.blob();
    const filename =
      parseContentDispositionFilename(response.headers.get("content-disposition")) || null;
    return { ok: true, status: response.status, data: blob, filename };
  } catch (error) {
    return { ok: false, error: error?.message || "Network error" };
  }
};

export const getRuns = (options) => request("/runs", undefined, options);

export const getObservabilityRuns = (options) =>
  request("/observability/runs", undefined, options);

export const getObservabilityRun = (id, options) =>
  request(`/observability/runs/${id}`, undefined, options);

export const getObservabilityRegistry = (options) =>
  request("/observability/registry", undefined, options);

export const getRunSummary = (id, options) =>
  request(`/runs/${id}/summary`, undefined, options);

export const getDecisions = (id, params, options) =>
  request(`/runs/${id}/decisions`, params, options);

export const getTrades = (id, params, options) =>
  request(`/runs/${id}/trades`, params, options);

export const getErrors = (id, params, options) =>
  request(`/runs/${id}/errors`, params, options);

export const getOhlcv = (id, params, options) =>
  request(`/runs/${id}/ohlcv`, params, options);

export const getTradeMarkers = (id, params, options) =>
  request(`/runs/${id}/trades/markers`, params, options);

export const getMetrics = (id, options) => request(`/runs/${id}/metrics`, undefined, options);

export const getTimeline = (id, params, options) =>
  request(`/runs/${id}/timeline`, params, options);

export const getActivePlugins = (options) => request("/plugins/active", undefined, options);

export const getFailedPlugins = (options) => request("/plugins/failed", undefined, options);

export const getStrategies = (options) => request("/strategies", undefined, options);

export const getDataImports = (options) => request("/data/imports", undefined, options);

export const importData = (file) => {
  const formData = new FormData();
  formData.append("file", file, file?.name || "dataset.csv");
  return postForm("/data/import", formData);
};

export const createProductRun = (payload) => post("/runs", payload);

export const createExperiment = async (payload) =>
  withCanonicalErrorInfo(
    await post("/experiments", payload, {
      headers: withUserHeader(),
    })
  );

export const getExperimentManifest = async (experimentId, options = {}) =>
  withCanonicalErrorInfo(
    await request(`/experiments/${experimentId}/manifest`, undefined, {
      ...options,
      headers: withUserHeader(options.headers),
    })
  );

export const getExperimentComparison = async (experimentId, options = {}) =>
  withCanonicalErrorInfo(
    await request(`/experiments/${experimentId}/comparison`, undefined, {
      ...options,
      headers: withUserHeader(options.headers),
    })
  );

export const getExperimentsIndex = async (options = {}) =>
  withCanonicalErrorInfo(
    await request("/experiments", undefined, {
      ...options,
      headers: withUserHeader(options.headers),
    })
  );

export const getRunStatus = (id, options) =>
  request(`/runs/${id}/status`, undefined, options);

export const getChatModes = () => request("/chat/modes");

export const postChat = (payload) => post("/chat", payload);

export const getRunReportExportUrl = (id) => buildApiUrl(`/runs/${id}/report/export`);

export const exportRunReport = (id) => requestBlob(`/runs/${id}/report/export`);

export const createRun = (payload, file) => {
  if (file) {
    const formData = new FormData();
    formData.append("request", JSON.stringify(payload || {}));
    formData.append("file", file, file.name || "upload.csv");
    return postForm("/runs", formData);
  }
  return post("/runs", payload);
};

const DEFAULT_API_BASE = "http://127.0.0.1:8000";
const API_VERSION_PATH = "/api/v1";

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
  if (typeof data.error === "string") {
    return data.error;
  }
  return fallback;
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

const request = async (path, params) => {
  const url = buildApiUrl(path, params);

  try {
    const response = await fetch(url);
    const contentType = response.headers.get("content-type") || "";
    let data;
    if (contentType.includes("application/json")) {
      data = await response.json();
    } else {
      data = await response.text();
    }

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

const post = async (path, payload) => {
  const url = buildApiUrl(path);
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
    const contentType = response.headers.get("content-type") || "";
    let data;
    if (contentType.includes("application/json")) {
      data = await response.json();
    } else {
      data = await response.text();
    }
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

export const getRuns = () => request("/runs");

export const getRunSummary = (id) => request(`/runs/${id}/summary`);

export const getDecisions = (id, params) => request(`/runs/${id}/decisions`, params);

export const getTrades = (id, params) => request(`/runs/${id}/trades`, params);

export const getErrors = (id, params) => request(`/runs/${id}/errors`, params);

export const getOhlcv = (id, params) => request(`/runs/${id}/ohlcv`, params);

export const getTradeMarkers = (id, params) => request(`/runs/${id}/trades/markers`, params);

export const getMetrics = (id) => request(`/runs/${id}/metrics`);

export const getTimeline = (id, params) => request(`/runs/${id}/timeline`, params);

export const getActivePlugins = () => request("/plugins/active");

export const getFailedPlugins = () => request("/plugins/failed");

export const getChatModes = () => request("/chat/modes");

export const postChat = (payload) => post("/chat", payload);

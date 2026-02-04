const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

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
  if (typeof data.detail === "string") {
    return data.detail;
  }
  if (typeof data.error === "string") {
    return data.error;
  }
  return fallback;
};

export const buildApiUrl = (path, params) => {
  const url = new URL(path, API_BASE);
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

export const getRuns = () => request("/api/runs");

export const getRunSummary = (id) => request(`/api/runs/${id}/summary`);

export const getDecisions = (id, params) => request(`/api/runs/${id}/decisions`, params);

export const getTrades = (id, params) => request(`/api/runs/${id}/trades`, params);

export const getErrors = (id, params) => request(`/api/runs/${id}/errors`, params);

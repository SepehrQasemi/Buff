const defaultApi = "http://127.0.0.1:8000/api/v1";
const defaultUi = "http://127.0.0.1:3000";

const apiBase = (process.env.NEXT_PUBLIC_API_BASE || process.env.API_BASE || defaultApi).replace(
  /\/+$/,
  ""
);
const uiBase = (process.env.UI_BASE || defaultUi).replace(/\/+$/, "");

const buildUrl = (base, path) => new URL(String(path || "").replace(/^\/+/, ""), `${base}/`).toString();

const requestJson = async (url) => {
  const response = await fetch(url);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${url} failed (${response.status}): ${text}`);
  }
  return response.json();
};

const requestText = async (url) => {
  const response = await fetch(url);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${url} failed (${response.status}): ${text}`);
  }
  return response.text();
};

const findRun = (runs) => {
  if (!Array.isArray(runs) || runs.length === 0) {
    return null;
  }
  const phase1 = runs.find((item) => item.id === "phase1_demo");
  return phase1 || runs[0];
};

const run = async () => {
  try {
    const runs = await requestJson(buildUrl(apiBase, "/runs"));
    const target = findRun(runs);
    if (!target) {
      throw new Error("No runs returned from API");
    }
    const runId = target.id;
    const html = await requestText(buildUrl(uiBase, `/runs/${runId}`));
    if (!html.includes("Chart Workspace")) {
      throw new Error("UI response missing workspace marker text");
    }
    if (target.artifacts?.trades) {
      const markers = await requestJson(buildUrl(apiBase, `/runs/${runId}/trades/markers`));
      if (!Array.isArray(markers.markers) || markers.markers.length === 0) {
        throw new Error("Expected non-empty trade markers for fixture run");
      }
    }

    const missingRun = await fetch(buildUrl(apiBase, "/runs/does-not-exist/summary"));
    if (missingRun.ok) {
      throw new Error("Expected non-200 response for missing run summary");
    }
    const missingPayload = await missingRun.json();
    if (!missingPayload.code || !missingPayload.message) {
      throw new Error("Missing run error payload missing code/message fields");
    }

    console.log("UI smoke OK", { runId });
  } catch (error) {
    console.error("UI smoke FAILED", error.message || error);
    process.exit(1);
  }
};

run();

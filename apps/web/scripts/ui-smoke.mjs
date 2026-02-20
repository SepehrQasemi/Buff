const apiBaseRaw = process.env.API_BASE_URL;
const uiBaseRaw = process.env.UI_BASE_URL;

const missing = [];
if (!apiBaseRaw) missing.push("API_BASE_URL");
if (!uiBaseRaw) missing.push("UI_BASE_URL");

if (missing.length) {
  const lines = [
    "UI smoke FAILED: missing required environment variables.",
    `Missing: ${missing.join(", ")}`,
    "API_BASE_URL is the API base URL.",
    "UI_BASE_URL is the UI base URL.",
    "",
    "Fix A (recommended): run `python scripts/verify_phase1.py --with-services --real-smoke`",
    "Fix B: set the variables manually:",
    "PowerShell:",
    '  $env:API_BASE_URL="http://127.0.0.1:8000"',
    '  $env:UI_BASE_URL="http://127.0.0.1:3000"',
    "Bash:",
    '  export API_BASE_URL="http://127.0.0.1:8000"',
    '  export UI_BASE_URL="http://127.0.0.1:3000"',
  ];
  console.error(lines.join("\n"));
  process.exit(2);
}

let apiBase = apiBaseRaw.replace(/\/+$/, "");
if (!apiBase.endsWith("/api/v1")) {
  apiBase = `${apiBase}/api/v1`;
}
const uiBase = uiBaseRaw.replace(/\/+$/, "");

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

const WORKSPACE_MARKER = 'data-testid="chart-workspace"';

const waitForMarker = async (url, marker, timeoutMs = 60000) => {
  const start = Date.now();
  let lastError;
  while (Date.now() - start < timeoutMs) {
    try {
      const html = await requestText(url);
      if (html.includes(marker)) {
        return html;
      }
      lastError = new Error(`Marker not found yet: ${marker}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  if (lastError) {
    throw lastError;
  }
  throw new Error(`Timed out waiting for marker: ${marker}`);
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
    await waitForMarker(buildUrl(uiBase, `/runs/${runId}`), WORKSPACE_MARKER);
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

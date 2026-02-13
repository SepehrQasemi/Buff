const defaultApi = "http://127.0.0.1:8000/api/v1";
const defaultUi = "http://127.0.0.1:3000";

const apiBase = (process.env.NEXT_PUBLIC_API_BASE || process.env.API_BASE || defaultApi).replace(
  /\/+$/,
  ""
);
const uiBase = (process.env.UI_BASE || defaultUi).replace(/\/+$/, "");
const runId = process.env.DEMO_RUN_ID || "stage5_demo";

const buildUrl = (base, path) =>
  new URL(String(path || "").replace(/^\/+/, ""), `${base}/`).toString();

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

const ensure = (condition, message) => {
  if (!condition) {
    throw new Error(message);
  }
};

const ensureNumber = (value, message) => {
  const num = Number(value);
  ensure(Number.isFinite(num), message);
};

const ensureNonEmptyString = (value, message) => {
  ensure(typeof value === "string" && value.trim().length > 0, message);
};

const ensureFields = (payload, fields, label) => {
  fields.forEach((field) => {
    ensure(payload && payload[field] !== undefined, `${label} missing '${field}'`);
  });
};

const run = async () => {
  try {
    const runs = await requestJson(buildUrl(apiBase, "/runs"));
    ensure(Array.isArray(runs), "Runs response must be an array");
    const target = runs.find((item) => item.id === runId);
    ensure(target, `Demo run '${runId}' not found in /runs`);
    ensure(target.status, "Run entry missing status");
    ensure(
      target.artifacts && typeof target.artifacts === "object",
      "Run entry missing artifacts config"
    );

    const summary = await requestJson(buildUrl(apiBase, `/runs/${runId}/summary`));
    ensureFields(summary, ["run_id", "artifacts", "risk"], "summary");
    ensure(summary.run_id === runId, "summary.run_id mismatch");
    ensure(
      summary.artifacts &&
        summary.artifacts.ohlcv &&
        summary.artifacts.trades &&
        summary.artifacts.metrics &&
        summary.artifacts.timeline,
      "summary artifacts missing required entries"
    );
    ensure(
      summary.risk && (summary.risk.reason || summary.risk.blocked !== null),
      "summary risk block reason missing"
    );

    const ohlcv = await requestJson(
      buildUrl(apiBase, `/runs/${runId}/ohlcv?timeframe=1m&limit=50`)
    );
    ensureFields(ohlcv, ["count", "candles"], "ohlcv");
    ensure(
      Array.isArray(ohlcv.candles) && ohlcv.candles.length >= 50,
      "ohlcv candles length < 50"
    );
    ensureFields(ohlcv.candles[0], ["ts", "open", "high", "low", "close", "volume"], "candle");

    const trades = await requestJson(
      buildUrl(apiBase, `/runs/${runId}/trades?page=1&page_size=50`)
    );
    ensureFields(trades, ["results"], "trades");
    ensure(Array.isArray(trades.results), "trades results must be an array");
    if (trades.results.length === 0) {
      const reason =
        trades.metadata?.reason ||
        trades.metadata?.message ||
        trades.reason ||
        trades.message;
      ensureNonEmptyString(reason, "trades empty without explicit reason metadata");
    }
    const tradeSample = trades.results[0];
    const timestampField =
      trades.timestamp_field ||
      Object.keys(tradeSample).find((key) =>
        ["timestamp", "timestamp_utc", "ts_utc", "ts", "time", "date"].includes(key)
      );
    ensure(timestampField, "trades missing timestamp field");
    ensure(tradeSample.price !== undefined, "trades missing price field");

    const metrics = await requestJson(buildUrl(apiBase, `/runs/${runId}/metrics`));
    ensureFields(metrics, ["total_return", "max_drawdown", "num_trades", "win_rate"], "metrics");
    ensureNumber(metrics.total_return, "metrics.total_return must be numeric");
    ensureNumber(metrics.max_drawdown, "metrics.max_drawdown must be numeric");
    ensureNumber(metrics.num_trades, "metrics.num_trades must be numeric");

    const timeline = await requestJson(buildUrl(apiBase, `/runs/${runId}/timeline`));
    ensureFields(timeline, ["events", "total"], "timeline");
    ensure(Array.isArray(timeline.events), "timeline events must be an array");
    if (timeline.events.length === 0) {
      const reason =
        timeline.metadata?.reason ||
        timeline.metadata?.message ||
        timeline.reason ||
        timeline.message;
      ensureNonEmptyString(reason, "timeline empty without explicit reason metadata");
    }
    const hasRiskBlock = timeline.events.some((event) => {
      if (!event) {
        return false;
      }
      const detail = event.detail ? String(event.detail) : "";
      const reason = event.risk && event.risk.reason ? String(event.risk.reason) : "";
      const type = event.type ? String(event.type).toLowerCase() : "";
      const severity = event.severity ? String(event.severity).toUpperCase() : "";
      const isRisk =
        type === "risk" || severity === "ERROR" || detail.toLowerCase().includes("block");
      if (!isRisk) {
        return false;
      }
      const text = reason || detail;
      return typeof text === "string" && /[a-zA-Z]/.test(text);
    });
    ensure(hasRiskBlock, "timeline missing risk block with human-readable reason");

    const plugins = await requestJson(buildUrl(apiBase, "/plugins/active"));
    ensure(Array.isArray(plugins.indicators), "plugins.indicators missing");
    ensure(Array.isArray(plugins.strategies), "plugins.strategies missing");
    ensure(
      plugins.indicators.some((item) => item.id === "demo_sma"),
      "demo_sma indicator not active"
    );
    ensure(
      plugins.strategies.some((item) => item.id === "demo_threshold"),
      "demo_threshold strategy not active"
    );

    const html = await requestText(buildUrl(uiBase, `/runs/${runId}`));
    ensure(html.includes('data-testid="chart-workspace"'), "workspace marker missing in UI");

    console.log("Demo render check OK", { runId });
  } catch (error) {
    console.error("Demo render check FAILED", error.message || error);
    process.exit(1);
  }
};

run();

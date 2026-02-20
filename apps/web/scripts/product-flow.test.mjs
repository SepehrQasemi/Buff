import assert from "assert";
import { mapApiErrorDetails } from "../lib/errorMapping.js";
import {
  deriveAvailableTimeframes,
  evaluateRiskPanelState,
} from "../lib/workspaceState.js";

const importApi = async () => {
  global.window = { __RUNTIME_CONFIG__: { API_BASE: "http://localhost:8000" } };
  return import(`../lib/api.js?cache=${Date.now()}-${Math.random()}`);
};

const makeCsvFile = () => {
  const body = "timestamp,open,high,low,close,volume\n2026-02-01T00:00:00Z,1,2,0.5,1.5,10\n";
  if (typeof File !== "undefined") {
    return new File([body], "sample.csv", { type: "text/csv" });
  }
  const blob = new Blob([body], { type: "text/csv" });
  blob.name = "sample.csv";
  return blob;
};

const jsonResponse = (payload, status = 200) =>
  new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });

const run = async () => {
  const api = await importApi();
  const calls = [];
  const queue = [];

  global.fetch = async (url, options = {}) => {
    calls.push({ url: String(url), options });
    const next = queue.shift();
    if (!next) {
      throw new Error(`Unexpected fetch call: ${url}`);
    }
    return next;
  };

  queue.push(
    jsonResponse({
      dataset_id: "abc123",
      manifest: { content_hash: "abc123", row_count: 1, columns: [] },
    })
  );
  const importResult = await api.importData(makeCsvFile());
  assert.strictEqual(importResult.ok, true, "importData should succeed");
  assert.ok(
    calls[0].url.endsWith("/api/v1/data/import"),
    "importData should target /api/v1/data/import"
  );

  queue.push(
    jsonResponse(
      {
        code: "DATA_INVALID",
        message: "CSV invalid",
        error_envelope: {
          error_code: "DATA_INVALID",
          human_message: "CSV missing required columns.",
          recovery_hint: "Use timestamp/open/high/low/close/volume headers.",
        },
      },
      400
    )
  );
  const createResult = await api.createProductRun({
    dataset_id: "abc123",
    strategy_id: "hold",
    params: {},
    risk_level: 3,
  });
  assert.strictEqual(createResult.ok, false, "createProductRun should surface API failures");
  const mapped = mapApiErrorDetails(createResult, "Run creation failed");
  assert.ok(mapped.summary.includes("CSV missing required columns."));
  assert.ok(
    mapped.actions.some((item) => item.includes("timestamp/open/high/low/close/volume")),
    "recovery hint should be preserved for UI rendering"
  );

  queue.push(
    jsonResponse({
      state: "RUNNING",
      percent: 70,
      last_event: { stage: "RUNNING", timestamp: "2026-02-01T00:00:00Z" },
    })
  );
  const statusResult = await api.getRunStatus("run_abc");
  assert.strictEqual(statusResult.ok, true);
  assert.strictEqual(statusResult.data.state, "RUNNING");
  assert.strictEqual(statusResult.data.percent, 70);
  assert.ok(calls[2].url.endsWith("/api/v1/runs/run_abc/status"));

  const availableTimeframes = deriveAvailableTimeframes(
    { ohlcv_available_timeframes: ["1m"] },
    "1h"
  );
  assert.deepStrictEqual(availableTimeframes, ["1m"]);
  assert.strictEqual(
    availableTimeframes.includes("1h"),
    false,
    "timeframe options should only include available artifact timeframes"
  );

  const summaryUnavailableRiskState = evaluateRiskPanelState({
    summary: null,
    summaryLoading: false,
    summaryError: { message: "summary unavailable" },
  });
  assert.strictEqual(
    summaryUnavailableRiskState.mode,
    "summary_unavailable",
    "risk warning should not show when summary is missing"
  );

  console.log("Product flow UI test OK");
};

await run();

const API_UNREACHABLE_MESSAGE = "API unreachable. Check that the backend is running.";
const RUN_NOT_INDEXED_MESSAGE =
  "Run not found in artifacts index. Check ARTIFACTS_ROOT and the run id.";
const MISSING_RUN_ID_MESSAGE =
  "Missing run id. Open /runs/stage5_demo or another valid run id.";
const MISSING_ARTIFACTS_MESSAGE =
  "Required artifacts are missing. Rebuild the run artifacts or update ARTIFACTS_ROOT.";

const extractErrorInfo = (payload) => {
  if (!payload || typeof payload !== "object") {
    return { code: null, message: null, details: null };
  }
  if (payload.error && typeof payload.error === "object") {
    return {
      code: payload.error.code || null,
      message: payload.error.message || null,
      details: payload.error.details || null,
    };
  }
  if (payload.detail && typeof payload.detail === "object") {
    return {
      code: payload.detail.code || null,
      message: payload.detail.message || null,
      details: payload.detail.details || null,
    };
  }
  return {
    code: payload.code || null,
    message: payload.message || null,
    details: payload.details || null,
  };
};

const missingArtifacts = {
  decision_records_missing: "decision_records.jsonl",
  ohlcv_missing: "OHLCV parquet",
  trades_missing: "trades.parquet",
  metrics_missing: "metrics.json",
  timeline_missing: "timeline.json",
  ARTIFACT_NOT_FOUND: "artifact",
};

const corruptedArtifacts = {
  decision_records_invalid: "decision_records.jsonl",
  ohlcv_invalid: "OHLCV parquet",
  trades_invalid: "trades.parquet",
  metrics_invalid: "metrics.json",
  timeline_invalid: "timeline.json",
};

const formatWithRunHint = (message, details) => {
  const runId = details && details.run_id ? details.run_id : null;
  if (!runId) {
    return message;
  }
  return `${message} (run: ${runId})`;
};

const mapErrorMessage = (code, details) => {
  if (code in missingArtifacts) {
    const artifact = missingArtifacts[code];
    return formatWithRunHint(
      `${artifact} missing. Ensure the demo artifacts pack is present under ARTIFACTS_ROOT.`,
      details
    );
  }
  if (code in corruptedArtifacts) {
    const artifact = corruptedArtifacts[code];
    return formatWithRunHint(
      `${artifact} is corrupted or unreadable. Rebuild the run artifacts.`,
      details
    );
  }
  if (code === "artifacts_root_missing") {
    return "Artifacts root not found. Set ARTIFACTS_ROOT to the demo artifacts folder.";
  }
  if (code === "invalid_run_id" || code === "RUN_CONFIG_INVALID") {
    return "Invalid run id. Use /runs/<id> with letters, numbers, and underscores.";
  }
  if (code === "run_not_found" || code === "RUN_NOT_FOUND") {
    return formatWithRunHint(
      "Run not found. Confirm the run id exists under ARTIFACTS_ROOT.",
      details
    );
  }
  if (code === "RUN_CORRUPTED") {
    return formatWithRunHint(
      "Run artifacts are missing or corrupted. Rebuild the run artifacts.",
      details
    );
  }
  return null;
};

const mapApiError = (result) => {
  if (!result || !result.status) {
    return null;
  }
  const { code, details } = extractErrorInfo(result.data);
  return code ? mapErrorMessage(code, details) : null;
};

const formatApiError = (result, fallback) => {
  if (!result) {
    return fallback;
  }
  if (!result.status) {
    return `${fallback}: ${result.error || API_UNREACHABLE_MESSAGE}`;
  }
  const { code, message, details } = extractErrorInfo(result.data);
  const mapped = code ? mapErrorMessage(code, details) : null;
  if (mapped) {
    return `${mapped} (HTTP ${result.status})`;
  }
  const text = message || result.error || fallback;
  return `${text} (HTTP ${result.status})`;
};

export {
  API_UNREACHABLE_MESSAGE,
  MISSING_RUN_ID_MESSAGE,
  MISSING_ARTIFACTS_MESSAGE,
  RUN_NOT_INDEXED_MESSAGE,
  extractErrorInfo,
  formatApiError,
  mapApiError,
};

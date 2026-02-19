const API_UNREACHABLE_MESSAGE = "API unreachable. Check that the backend is running.";
const RUN_NOT_INDEXED_MESSAGE =
  "Run not found in registry. Check RUNS_ROOT (or ARTIFACTS_ROOT in demo mode) and the run id.";
const MISSING_RUN_ID_MESSAGE =
  "Missing run id. Open /runs/stage5_demo or another valid run id.";
const MISSING_ARTIFACTS_MESSAGE =
  "Required artifacts are missing. Rebuild the run artifacts or update RUNS_ROOT.";

const extractErrorInfo = (payload) => {
  if (!payload || typeof payload !== "object") {
    return { code: null, message: null, details: null, envelope: null };
  }
  const directEnvelope =
    payload.error_envelope ||
    payload.error?.envelope ||
    payload.details?.error_envelope ||
    payload.error?.details?.error_envelope ||
    null;
  if (payload.error && typeof payload.error === "object") {
    return {
      code: payload.error.code || null,
      message: payload.error.message || null,
      details: payload.error.details || null,
      envelope: directEnvelope,
    };
  }
  if (payload.detail && typeof payload.detail === "object") {
    return {
      code: payload.detail.code || null,
      message: payload.detail.message || null,
      details: payload.detail.details || null,
      envelope: directEnvelope,
    };
  }
  return {
    code: payload.code || null,
    message: payload.message || null,
    details: payload.details || null,
    envelope: directEnvelope,
  };
};

const ERROR_HINTS = {
  RUNS_ROOT_UNSET: {
    title: "RUNS_ROOT is not set",
    fix: "Set RUNS_ROOT to a writable folder and restart the API.",
  },
  RUNS_ROOT_MISSING: {
    title: "RUNS_ROOT directory is missing",
    fix: "Create the RUNS_ROOT directory and restart the API.",
  },
  RUNS_ROOT_INVALID: {
    title: "RUNS_ROOT must be a directory",
    fix: "Point RUNS_ROOT to a directory path and restart the API.",
  },
  RUNS_ROOT_NOT_WRITABLE: {
    title: "RUNS_ROOT is not writable",
    fix: "Fix permissions or choose another folder and restart the API.",
  },
  DATA_SOURCE_NOT_FOUND: {
    title: "CSV source file not found",
    fix: "Update data_source.path to a CSV file that exists on the API host.",
  },
  DATA_INVALID: {
    title: "CSV data invalid",
    fix: "Ensure required columns exist and timestamps are 1m with no gaps, then re-export.",
  },
  trades_missing: {
    title: "Trades artifact missing",
    fix: "Ensure trades.jsonl or trades.parquet exists under RUNS_ROOT (or ARTIFACTS_ROOT in demo mode).",
  },
  trades_invalid: {
    title: "Trades artifact invalid",
    fix: "Rebuild trades.jsonl/trades.parquet for this run under RUNS_ROOT.",
  },
  ohlcv_missing: {
    title: "OHLCV artifact missing",
    fix: "Ensure ohlcv_*.jsonl or ohlcv_*.parquet exists under RUNS_ROOT (or ARTIFACTS_ROOT in demo mode).",
  },
  ohlcv_invalid: {
    title: "OHLCV artifact invalid",
    fix: "Rebuild the OHLCV artifact for this run under RUNS_ROOT.",
  },
  metrics_missing: {
    title: "Metrics artifact missing",
    fix: "Ensure metrics.json exists under RUNS_ROOT (or ARTIFACTS_ROOT in demo mode).",
  },
  metrics_invalid: {
    title: "Metrics artifact invalid",
    fix: "Rebuild metrics.json for this run under RUNS_ROOT.",
  },
  timeline_missing: {
    title: "Timeline artifact missing",
    fix: "Ensure timeline.json exists under RUNS_ROOT (or ARTIFACTS_ROOT in demo mode).",
  },
  timeline_invalid: {
    title: "Timeline artifact invalid",
    fix: "Rebuild timeline.json for this run under RUNS_ROOT.",
  },
  decision_records_missing: {
    title: "Decision records missing",
    fix: "Ensure decision_records.jsonl exists under RUNS_ROOT (or ARTIFACTS_ROOT in demo mode).",
  },
  decision_records_invalid: {
    title: "Decision records invalid",
    fix: "Rebuild decision_records.jsonl for this run under RUNS_ROOT.",
  },
  artifacts_root_missing: {
    title: "Artifacts root not found",
    fix: "Set ARTIFACTS_ROOT to the demo artifacts folder and restart the API.",
  },
};

const missingArtifacts = {
  decision_records_missing: "decision_records.jsonl",
  ohlcv_missing: "OHLCV artifact",
  trades_missing: "trades artifact",
  metrics_missing: "metrics.json",
  timeline_missing: "timeline.json",
  ARTIFACT_NOT_FOUND: "artifact",
};

const corruptedArtifacts = {
  decision_records_invalid: "decision_records.jsonl",
  ohlcv_invalid: "OHLCV artifact",
  trades_invalid: "trades artifact",
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

const formatHintMessage = (hint, details) => {
  const title = hint?.title ? String(hint.title) : "Request failed";
  const fix = hint?.fix ? String(hint.fix) : "Check the API logs for details.";
  return `${formatWithRunHint(title, details)} Fix: ${fix}`;
};

const mapErrorMessage = (code, details) => {
  if (code && ERROR_HINTS[code]) {
    return formatHintMessage(ERROR_HINTS[code], details);
  }
  if (code in missingArtifacts) {
    const artifact = missingArtifacts[code];
    return formatWithRunHint(
      `${artifact} missing. Ensure the artifact exists under RUNS_ROOT (or ARTIFACTS_ROOT in demo mode).`,
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
  if (code === "invalid_run_id" || code === "RUN_CONFIG_INVALID") {
    return "Invalid run id. Use /runs/<id> with letters, numbers, and underscores.";
  }
  if (code === "run_not_found" || code === "RUN_NOT_FOUND") {
    return formatWithRunHint(
      "Run not found. Confirm the run id exists under RUNS_ROOT (or ARTIFACTS_ROOT in demo mode).",
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
  ERROR_HINTS,
  extractErrorInfo,
  formatApiError,
  mapApiError,
};

import { API_UNREACHABLE_MESSAGE, extractErrorInfo } from "./errors.js";

const DOCS_FIRST_RUN = "/docs/FIRST_RUN.md#troubleshooting";
const DOCS_CSV = "/docs/FIRST_RUN.md#csv-requirements";

const ARTIFACT_MISSING = {
  decision_records_missing: "decision_records.jsonl",
  ohlcv_missing: "OHLCV artifact",
  trades_missing: "trades.jsonl or trades.parquet",
  metrics_missing: "metrics.json",
  timeline_missing: "timeline.json",
  ARTIFACT_NOT_FOUND: "artifact",
};

const ARTIFACT_INVALID = {
  decision_records_invalid: "decision_records.jsonl",
  ohlcv_invalid: "OHLCV artifact",
  trades_invalid: "trades artifact",
  metrics_invalid: "metrics.json",
  timeline_invalid: "timeline.json",
};

const normalizeError = (error) => {
  if (!error) {
    return null;
  }
  if (typeof error === "string") {
    return {
      title: "Request failed",
      summary: error,
      actions: [],
      help: null,
      short: error,
    };
  }
  return error;
};

const buildError = ({
  title,
  summary,
  actions = [],
  help = null,
  code = null,
  status = null,
  details = null,
}) => ({
  title,
  summary,
  actions,
  help,
  code,
  status,
  details,
  short: summary || title,
});

const parseMissingColumn = (message) => {
  if (!message) {
    return null;
  }
  const match = String(message).match(/Missing required column:\s*([^\s]+)/i);
  if (match) {
    return match[1];
  }
  if (String(message).toLowerCase().includes("timestamp column missing")) {
    return "timestamp";
  }
  return null;
};

const mapErrorPayload = ({ code, message, details, status, fallback } = {}) => {
  if (!code && !message) {
    return null;
  }
  const normalizedCode = code ? String(code) : null;
  const baseTitle = fallback || "Request failed";
  const baseSummary = message || fallback || "Request failed";

  if (normalizedCode === "RUNS_ROOT_UNSET") {
    const envName = details?.env || "RUNS_ROOT";
    return buildError({
      code: normalizedCode,
      status,
      details,
      title: "RUNS_ROOT is not set",
      summary: `Set ${envName} to a writable folder and restart the API.`,
      actions: [`Set ${envName} and restart the API.`],
      help: { label: "First run guide", href: DOCS_FIRST_RUN },
    });
  }

  if (
    normalizedCode === "RUNS_ROOT_MISSING" ||
    normalizedCode === "RUNS_ROOT_INVALID" ||
    normalizedCode === "RUNS_ROOT_NOT_WRITABLE"
  ) {
    return buildError({
      code: normalizedCode,
      status,
      details,
      title: "RUNS_ROOT is not ready",
      summary: message || "RUNS_ROOT is missing or not writable.",
      actions: ["Fix RUNS_ROOT permissions or choose another folder.", "Restart the API."],
      help: { label: "First run guide", href: DOCS_FIRST_RUN },
    });
  }

  if (normalizedCode === "RUN_CONFIG_INVALID") {
    return buildError({
      code: normalizedCode,
      status,
      details,
      title: "Run configuration invalid",
      summary: message || "Check the inputs and try again.",
      actions: ["Verify CSV, symbol, timeframe, and strategy fields."],
    });
  }

  if (normalizedCode === "RUN_ID_INVALID" || normalizedCode === "invalid_run_id") {
    return buildError({
      code: normalizedCode,
      status,
      details,
      title: "Invalid run id",
      summary: "Run id must use letters, numbers, underscores, or hyphens.",
      actions: ["Use /runs/<id> with a valid id format."],
    });
  }

  if (normalizedCode === "DATA_INVALID") {
    const missingColumn = parseMissingColumn(message);
    const summary = missingColumn
      ? `Missing required column: ${missingColumn}.`
      : message || "CSV data failed validation.";
    return buildError({
      code: normalizedCode,
      status,
      details,
      title: "CSV data invalid",
      summary,
      actions: [
        "Ensure columns: timestamp, open, high, low, close, volume.",
        "Use 1m data with strictly increasing timestamps.",
      ],
      help: { label: "CSV requirements", href: DOCS_CSV },
    });
  }

  if (normalizedCode === "DATA_SOURCE_NOT_FOUND") {
    return buildError({
      code: normalizedCode,
      status,
      details,
      title: "CSV source file not found",
      summary: message || "The CSV path could not be resolved on the API host.",
      actions: ["Upload the CSV file or update data_source.path."],
    });
  }

  if (normalizedCode === "RUN_NOT_FOUND" || normalizedCode === "run_not_found") {
    return buildError({
      code: normalizedCode,
      status,
      details,
      title: "Run not found",
      summary: message || "The requested run does not exist.",
      actions: ["Check the run id and RUNS_ROOT.", "Create a new run if needed."],
    });
  }

  if (normalizedCode === "RUN_CORRUPTED") {
    return buildError({
      code: normalizedCode,
      status,
      details,
      title: "Run artifacts missing",
      summary: message || "Run artifacts are missing or corrupted.",
      actions: ["Recreate the run to regenerate artifacts."],
    });
  }

  if (normalizedCode && normalizedCode in ARTIFACT_MISSING) {
    const artifact = details?.name || ARTIFACT_MISSING[normalizedCode];
    return buildError({
      code: normalizedCode,
      status,
      details,
      title: "Artifact missing",
      summary: `${artifact} is missing.`,
      actions: ["Recreate the run or restore the missing artifact."],
    });
  }

  if (normalizedCode && normalizedCode in ARTIFACT_INVALID) {
    const artifact = ARTIFACT_INVALID[normalizedCode];
    return buildError({
      code: normalizedCode,
      status,
      details,
      title: "Artifact invalid",
      summary: `${artifact} is corrupted or unreadable.`,
      actions: ["Recreate the run to regenerate artifacts."],
    });
  }

  return buildError({
    code: normalizedCode,
    status,
    details,
    title: baseTitle,
    summary: baseSummary,
    actions: ["Check the API logs for details."],
  });
};

const mapApiErrorDetails = (result, fallback) => {
  if (!result) {
    return null;
  }
  if (!result.status) {
    return buildError({
      title: "API unreachable",
      summary: result.error || API_UNREACHABLE_MESSAGE,
      actions: ["Start the API and retry the request."],
      help: { label: "First run guide", href: DOCS_FIRST_RUN },
      code: "API_UNREACHABLE",
    });
  }
  const { code, message, details } = extractErrorInfo(result.data);
  return mapErrorPayload({ code, message, details, status: result.status, fallback });
};

const buildClientError = ({ title, summary, actions = [], help = null }) =>
  buildError({
    title,
    summary,
    actions,
    help,
    code: "CLIENT_ERROR",
  });

const formatErrorInline = (error) => {
  const normalized = normalizeError(error);
  if (!normalized) {
    return null;
  }
  return normalized.short || normalized.summary || normalized.title;
};

export { buildClientError, formatErrorInline, mapApiErrorDetails, mapErrorPayload, normalizeError };

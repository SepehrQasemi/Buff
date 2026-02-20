import { API_UNREACHABLE_MESSAGE, extractErrorInfo } from "./errors.js";

const HELP_FIRST_RUN = "/help#first-run";
const HELP_RUNS_ROOT = "/help#runs-root";
const HELP_DATASET_MISSING = "/help#dataset-missing";
const HELP_RUN_STUCK = "/help#run-stuck";
const HELP_BACKEND_VERIFY = "/help#backend-verify";
const HELP_LOGS_REPORT = "/help#logs-report";

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
  envelope = null,
}) => ({
  title,
  summary,
  actions,
  help,
  code,
  status,
  details,
  envelope,
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

const _normalizeEnvelope = (value) => {
  if (!value || typeof value !== "object") {
    return null;
  }
  const provenance = value.provenance && typeof value.provenance === "object" ? value.provenance : {};
  return {
    error_code: value.error_code || null,
    human_message: value.human_message || null,
    recovery_hint: value.recovery_hint || null,
    artifact_reference: value.artifact_reference || null,
    provenance,
  };
};

const _applyEnvelope = (mapped, envelope) => {
  const normalized = _normalizeEnvelope(envelope);
  if (!mapped || !normalized) {
    return mapped;
  }
  const nextActions = [...(mapped.actions || [])];
  if (normalized.recovery_hint && !nextActions.includes(normalized.recovery_hint)) {
    nextActions.unshift(normalized.recovery_hint);
  }
  return {
    ...mapped,
    summary: normalized.human_message || mapped.summary,
    actions: nextActions,
    envelope: normalized,
    short: normalized.human_message || mapped.short,
  };
};

const mapErrorPayload = ({ code, message, details, status, fallback, envelope } = {}) => {
  if (!code && !message) {
    return null;
  }
  const normalizedCode = code ? String(code) : null;
  const baseTitle = fallback || "Request failed";
  const baseSummary = message || fallback || "Request failed";

  if (normalizedCode === "RUNS_ROOT_UNSET") {
    const envName = details?.env || "RUNS_ROOT";
    return _applyEnvelope(
      buildError({
      code: normalizedCode,
      status,
      details,
      title: "RUNS_ROOT is not set",
      summary: `Set ${envName} to a writable folder and restart the API.`,
      actions: [`Set ${envName} and restart the API.`],
      help: { label: "First run checklist", href: HELP_FIRST_RUN },
      }),
      envelope
    );
  }

  if (
    normalizedCode === "RUNS_ROOT_MISSING" ||
    normalizedCode === "RUNS_ROOT_INVALID" ||
    normalizedCode === "RUNS_ROOT_NOT_WRITABLE"
  ) {
    return _applyEnvelope(
      buildError({
      code: normalizedCode,
      status,
      details,
      title: "RUNS_ROOT is not ready",
      summary: message || "RUNS_ROOT is missing or not writable.",
      actions: ["Fix RUNS_ROOT permissions or choose another folder.", "Restart the API."],
      help: { label: "Fix RUNS_ROOT", href: HELP_RUNS_ROOT },
      }),
      envelope
    );
  }

  if (normalizedCode === "RUN_CONFIG_INVALID") {
    return _applyEnvelope(
      buildError({
      code: normalizedCode,
      status,
      details,
      title: "Run configuration invalid",
      summary: message || "Check the inputs and try again.",
      actions: ["Verify CSV, symbol, timeframe, and strategy fields."],
      }),
      envelope
    );
  }

  if (normalizedCode === "RUN_ID_INVALID" || normalizedCode === "invalid_run_id") {
    return _applyEnvelope(
      buildError({
      code: normalizedCode,
      status,
      details,
      title: "Invalid run id",
      summary: "Run id must use letters, numbers, underscores, or hyphens.",
      actions: ["Use /runs/<id> with a valid id format."],
      }),
      envelope
    );
  }

  if (normalizedCode === "DATA_INVALID") {
    const missingColumn = parseMissingColumn(message);
    const summary = missingColumn
      ? `Missing required column: ${missingColumn}.`
      : message || "CSV data failed validation.";
    return _applyEnvelope(
      buildError({
      code: normalizedCode,
      status,
      details,
      title: "CSV data invalid",
      summary,
      actions: [
        "Ensure columns: timestamp, open, high, low, close, volume.",
        "Use 1m data with strictly increasing timestamps.",
      ],
      help: { label: "Dataset troubleshooting", href: HELP_DATASET_MISSING },
      }),
      envelope
    );
  }

  if (normalizedCode === "DATA_SOURCE_NOT_FOUND") {
    return _applyEnvelope(
      buildError({
      code: normalizedCode,
      status,
      details,
      title: "CSV source file not found",
      summary: message || "The CSV path could not be resolved on the API host.",
      actions: ["Upload the CSV file or update data_source.path."],
      help: { label: "Dataset troubleshooting", href: HELP_DATASET_MISSING },
      }),
      envelope
    );
  }

  if (normalizedCode === "RUN_NOT_FOUND" || normalizedCode === "run_not_found") {
    return _applyEnvelope(
      buildError({
      code: normalizedCode,
      status,
      details,
      title: "Run not found",
      summary: message || "The requested run does not exist.",
      actions: ["Check the run id and RUNS_ROOT.", "Create a new run if needed."],
      help: { label: "Run stuck troubleshooting", href: HELP_RUN_STUCK },
      }),
      envelope
    );
  }

  if (normalizedCode === "RUN_CORRUPTED") {
    return _applyEnvelope(
      buildError({
      code: normalizedCode,
      status,
      details,
      title: "Run artifacts missing",
      summary: message || "Run artifacts are missing or corrupted.",
      actions: ["Recreate the run to regenerate artifacts."],
      help: { label: "Logs and report bundle", href: HELP_LOGS_REPORT },
      }),
      envelope
    );
  }

  if (normalizedCode && normalizedCode in ARTIFACT_MISSING) {
    const artifact = details?.name || ARTIFACT_MISSING[normalizedCode];
    return _applyEnvelope(
      buildError({
      code: normalizedCode,
      status,
      details,
      title: "Artifact missing",
      summary: `${artifact} is missing.`,
      actions: ["Recreate the run or restore the missing artifact."],
      help: { label: "Logs and report bundle", href: HELP_LOGS_REPORT },
      }),
      envelope
    );
  }

  if (normalizedCode && normalizedCode in ARTIFACT_INVALID) {
    const artifact = ARTIFACT_INVALID[normalizedCode];
    return _applyEnvelope(
      buildError({
      code: normalizedCode,
      status,
      details,
      title: "Artifact invalid",
      summary: `${artifact} is corrupted or unreadable.`,
      actions: ["Recreate the run to regenerate artifacts."],
      help: { label: "Logs and report bundle", href: HELP_LOGS_REPORT },
      }),
      envelope
    );
  }

  return _applyEnvelope(
    buildError({
      code: normalizedCode,
      status,
      details,
      title: baseTitle,
      summary: baseSummary,
      actions: ["Check the API logs for details."],
      help: { label: "Logs and report bundle", href: HELP_LOGS_REPORT },
    }),
    envelope
  );
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
      help: { label: "Verify backend health", href: HELP_BACKEND_VERIFY },
      code: "API_UNREACHABLE",
    });
  }
  const { code, message, details, envelope } = extractErrorInfo(result.data);
  return mapErrorPayload({
    code,
    message,
    details,
    status: result.status,
    fallback,
    envelope,
  });
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

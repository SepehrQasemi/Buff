import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useMemo, useRef, useState } from "react";
import ErrorNotice from "../../components/ErrorNotice";
import {
  createProductRun,
  getDataImports,
  getRunStatus,
  getStrategies,
  importData,
} from "../../lib/api";
import { buildClientError, mapApiErrorDetails } from "../../lib/errorMapping";

const STEP_IMPORT = 1;
const STEP_STRATEGY = 2;
const STEP_CONFIGURE = 3;
const STEP_RUN = 4;
const INIT_POLL_DELAY_MS = 1200;
const INIT_RETRY_DELAY_MS = 1800;

const initializationBadgeKind = (state) => {
  const normalized = String(state || "").toUpperCase();
  if (normalized === "FAILED" || normalized === "CORRUPTED") {
    return "invalid";
  }
  if (normalized === "RUNNING" || normalized === "COMPLETED" || normalized === "OK") {
    return "ok";
  }
  return "info";
};

const RISK_LEVEL_OPTIONS = [
  { value: 1, label: "Conservative" },
  { value: 3, label: "Balanced" },
  { value: 5, label: "Aggressive" },
];

const PARAM_TEXT_TYPES = new Set(["string"]);
const PARAM_INTEGER_TYPES = new Set(["integer", "int"]);
const PARAM_NUMBER_TYPES = new Set(["number", "float"]);
const PARAM_BOOLEAN_TYPES = new Set(["boolean", "bool"]);

const isObject = (value) => Boolean(value) && typeof value === "object" && !Array.isArray(value);

const normalizeSchemaType = (rawType) => {
  if (Array.isArray(rawType)) {
    const first = rawType.find((value) => typeof value === "string");
    return String(first || "").toLowerCase();
  }
  return String(rawType || "").toLowerCase();
};

const formatTimeRange = (range) => {
  if (!isObject(range)) {
    return "n/a";
  }
  const start = range.start_ts || "n/a";
  const end = range.end_ts || "n/a";
  return `${start} to ${end}`;
};

const normalizeDataset = (item) => {
  if (!isObject(item)) {
    return null;
  }
  const id = String(item.content_hash || "").trim().toLowerCase();
  if (!id) {
    return null;
  }
  return {
    content_hash: id,
    filename: String(item.filename || "dataset.csv"),
    row_count: Number(item.row_count || 0),
    columns: Array.isArray(item.columns) ? item.columns.map((col) => String(col)) : [],
    inferred_time_range: isObject(item.inferred_time_range) ? item.inferred_time_range : {},
    imported_at: item.imported_at || null,
  };
};

const normalizeStrategy = (item) => {
  if (!isObject(item)) {
    return null;
  }
  const id = String(item.id || "").trim();
  if (!id) {
    return null;
  }
  return {
    id,
    display_name: String(item.display_name || id),
    description: String(item.description || ""),
    param_schema: isObject(item.param_schema) ? item.param_schema : {},
    default_params: isObject(item.default_params) ? item.default_params : {},
    tags: Array.isArray(item.tags) ? item.tags.map((tag) => String(tag)) : [],
  };
};

const getParamDefaultValue = (name, schema, defaults) => {
  if (isObject(defaults) && Object.prototype.hasOwnProperty.call(defaults, name)) {
    return defaults[name];
  }
  if (isObject(schema) && Object.prototype.hasOwnProperty.call(schema, "default")) {
    return schema.default;
  }
  return "";
};

const getStrategyParameters = (strategy) => {
  if (!strategy) {
    return [];
  }
  const schema = isObject(strategy.param_schema) ? strategy.param_schema : {};
  const properties = isObject(schema.properties) ? schema.properties : {};
  const requiredList = Array.isArray(schema.required) ? schema.required : [];
  const required = new Set(requiredList.map((value) => String(value)));

  return Object.keys(properties)
    .sort()
    .map((name) => {
      const propertySchema = isObject(properties[name]) ? properties[name] : {};
      return {
        name,
        schema: propertySchema,
        required: required.has(name),
        type: normalizeSchemaType(propertySchema.type),
        defaultValue: getParamDefaultValue(name, propertySchema, strategy.default_params),
      };
    });
};

const coerceParameterValue = (parameter, value) => {
  const type = parameter.type;
  const schema = parameter.schema;

  if (value === null || value === undefined || value === "") {
    if (parameter.required) {
      return {
        ok: false,
        error: `${parameter.name} is required.`,
      };
    }
    return { ok: true, skip: true };
  }

  if (Array.isArray(schema.enum) && schema.enum.length > 0) {
    if (!schema.enum.includes(value)) {
      return {
        ok: false,
        error: `${parameter.name} must be one of: ${schema.enum.join(", ")}`,
      };
    }
  }

  if (PARAM_BOOLEAN_TYPES.has(type)) {
    return { ok: true, value: Boolean(value) };
  }

  if (PARAM_INTEGER_TYPES.has(type)) {
    const parsed = Number.parseInt(String(value), 10);
    if (!Number.isFinite(parsed)) {
      return { ok: false, error: `${parameter.name} must be an integer.` };
    }
    if (Number.isFinite(schema.minimum) && parsed < schema.minimum) {
      return { ok: false, error: `${parameter.name} must be >= ${schema.minimum}.` };
    }
    if (Number.isFinite(schema.maximum) && parsed > schema.maximum) {
      return { ok: false, error: `${parameter.name} must be <= ${schema.maximum}.` };
    }
    return { ok: true, value: parsed };
  }

  if (PARAM_NUMBER_TYPES.has(type)) {
    const parsed = Number.parseFloat(String(value));
    if (!Number.isFinite(parsed)) {
      return { ok: false, error: `${parameter.name} must be a number.` };
    }
    if (Number.isFinite(schema.minimum) && parsed < schema.minimum) {
      return { ok: false, error: `${parameter.name} must be >= ${schema.minimum}.` };
    }
    if (Number.isFinite(schema.maximum) && parsed > schema.maximum) {
      return { ok: false, error: `${parameter.name} must be <= ${schema.maximum}.` };
    }
    return { ok: true, value: parsed };
  }

  if (PARAM_TEXT_TYPES.has(type) || !type) {
    return { ok: true, value: String(value) };
  }

  return { ok: true, value };
};

const buildRunParameters = (parameters, values) => {
  const output = {};
  for (const parameter of parameters) {
    const rawValue = values[parameter.name];
    const normalized = coerceParameterValue(parameter, rawValue);
    if (!normalized.ok) {
      return { ok: false, error: normalized.error };
    }
    if (normalized.skip) {
      continue;
    }
    output[parameter.name] = normalized.value;
  }
  return { ok: true, value: output };
};

const mergeDatasets = (existing, incoming) => {
  const byId = new Map();
  for (const item of existing) {
    byId.set(item.content_hash, item);
  }
  for (const item of incoming) {
    byId.set(item.content_hash, item);
  }
  return Array.from(byId.values()).sort((a, b) => a.content_hash.localeCompare(b.content_hash));
};

const stepClass = (currentStep, step) => {
  if (currentStep === step) {
    return "step-pill step-pill-active";
  }
  if (currentStep > step) {
    return "step-pill step-pill-complete";
  }
  return "step-pill";
};

export default function RunsNewPage() {
  const router = useRouter();
  const hiddenFileInput = useRef(null);

  const [step, setStep] = useState(STEP_IMPORT);
  const [strategies, setStrategies] = useState([]);
  const [datasets, setDatasets] = useState([]);
  const [loadingInitial, setLoadingInitial] = useState(true);
  const [error, setError] = useState(null);
  const [info, setInfo] = useState(null);

  const [selectedFile, setSelectedFile] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [importing, setImporting] = useState(false);

  const [datasetId, setDatasetId] = useState("");
  const [datasetManifest, setDatasetManifest] = useState(null);

  const [strategyId, setStrategyId] = useState("");
  const [parameterValues, setParameterValues] = useState({});
  const [riskLevel, setRiskLevel] = useState(3);
  const [creatingRun, setCreatingRun] = useState(false);
  const [createdRunId, setCreatedRunId] = useState("");
  const [initializingRun, setInitializingRun] = useState(false);
  const [initializationStatus, setInitializationStatus] = useState({
    state: "CREATED",
    percent: 0,
    lastEvent: null,
  });
  const [initializationError, setInitializationError] = useState(null);

  const selectedStrategy = useMemo(
    () => strategies.find((strategy) => strategy.id === strategyId) || null,
    [strategies, strategyId]
  );
  const strategyParameters = useMemo(
    () => getStrategyParameters(selectedStrategy),
    [selectedStrategy]
  );
  const selectedDataset = useMemo(
    () =>
      datasetManifest ||
      datasets.find((item) => item.content_hash === datasetId) ||
      null,
    [datasetManifest, datasets, datasetId]
  );

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoadingInitial(true);
      const [strategiesResult, importsResult] = await Promise.all([
        getStrategies(),
        getDataImports(),
      ]);
      if (!active) {
        return;
      }

      const nextStrategies = strategiesResult.ok
        ? (Array.isArray(strategiesResult.data)
            ? strategiesResult.data.map(normalizeStrategy).filter(Boolean)
            : [])
        : [];
      const nextDatasets = importsResult.ok
        ? (Array.isArray(importsResult.data?.datasets)
            ? importsResult.data.datasets.map(normalizeDataset).filter(Boolean)
            : [])
        : [];

      if (!strategiesResult.ok) {
        setError(mapApiErrorDetails(strategiesResult, "Failed to load strategies"));
      } else if (!importsResult.ok) {
        setError(mapApiErrorDetails(importsResult, "Failed to load imported datasets"));
      } else {
        setError(null);
      }

      setStrategies(nextStrategies);
      setDatasets(nextDatasets);
      setLoadingInitial(false);
    };

    load();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedStrategy) {
      setParameterValues({});
      return;
    }
    const defaults = {};
    for (const parameter of getStrategyParameters(selectedStrategy)) {
      defaults[parameter.name] = parameter.defaultValue;
    }
    setParameterValues(defaults);
  }, [selectedStrategy]);

  useEffect(() => {
    if (!createdRunId || !initializingRun) {
      return undefined;
    }
    let active = true;
    let timerId = null;
    let inFlight = false;

    const schedule = (delayMs) => {
      if (!active) {
        return;
      }
      if (timerId) {
        clearTimeout(timerId);
      }
      timerId = setTimeout(poll, delayMs);
    };

    const poll = async () => {
      if (!active || inFlight) {
        return;
      }
      inFlight = true;
      const result = await getRunStatus(createdRunId, { bypassCache: true });
      inFlight = false;
      if (!active) {
        return;
      }

      if (!result.ok) {
        if (!result.status || result.status !== 404) {
          setInitializationError(
            mapApiErrorDetails(result, "Waiting for run lifecycle update")
          );
        }
        schedule(INIT_RETRY_DELAY_MS);
        return;
      }

      setInitializationError(null);
      const payload = result.data && typeof result.data === "object" ? result.data : {};
      const state = String(payload.state || "CREATED").toUpperCase();
      const percent = Number.isFinite(payload.percent) ? payload.percent : 0;
      const lastEvent =
        payload.last_event && typeof payload.last_event === "object"
          ? payload.last_event
          : null;
      setInitializationStatus({ state, percent, lastEvent });
      if (state !== "CREATED") {
        setInitializingRun(false);
        setInfo(`Run created: ${createdRunId}. State is ${state}. Redirecting...`);
        router.push(`/runs/${createdRunId}`);
        return;
      }

      schedule(INIT_POLL_DELAY_MS);
    };

    poll();
    return () => {
      active = false;
      if (timerId) {
        clearTimeout(timerId);
      }
    };
  }, [createdRunId, initializingRun, router]);

  const canProceedToStrategy = Boolean(datasetId);
  const canProceedToConfigure = canProceedToStrategy && Boolean(strategyId);
  const canCreateRun = canProceedToConfigure && Number.isInteger(riskLevel);

  const selectDataset = (dataset) => {
    if (!dataset?.content_hash) {
      return;
    }
    setDatasetId(dataset.content_hash);
    setDatasetManifest(dataset);
    setInfo(`Selected dataset ${dataset.content_hash.slice(0, 12)}...`);
    setError(null);
    setStep(STEP_STRATEGY);
  };

  const onFilePicked = (file) => {
    if (!file) {
      return;
    }
    setSelectedFile(file);
    setInfo(`Selected file: ${file.name}`);
    setError(null);
  };

  const handleImportData = async () => {
    if (!selectedFile) {
      setError(
        buildClientError({
          title: "CSV file required",
          summary: "Select a CSV file before importing data.",
          actions: ["Pick a CSV file with timestamp/open/high/low/close/volume columns."],
        })
      );
      return;
    }
    setImporting(true);
    setError(null);
    setInfo("Importing CSV...");
    const result = await importData(selectedFile);
    if (!result.ok) {
      setImporting(false);
      setInfo(null);
      setError(mapApiErrorDetails(result, "Data import failed"));
      return;
    }
    const importedId = String(result.data?.dataset_id || "");
    const manifest = normalizeDataset(result.data?.manifest);
    if (!importedId || !manifest) {
      setImporting(false);
      setInfo(null);
      setError(
        buildClientError({
          title: "Import response invalid",
          summary: "Server response did not include dataset details.",
          actions: ["Retry import. If it persists, check API logs."],
        })
      );
      return;
    }
    setDatasetId(importedId);
    setDatasetManifest(manifest);
    setDatasets((current) => mergeDatasets(current, [manifest]));
    setImporting(false);
    setStep(STEP_STRATEGY);
    setInfo(`Import complete. Dataset id: ${importedId}`);
  };

  const handleCreateRun = async () => {
    if (!canCreateRun) {
      setError(
        buildClientError({
          title: "Missing required fields",
          summary: "Import data, select a strategy, and choose a risk level before creating a run.",
        })
      );
      return;
    }
    const paramsResult = buildRunParameters(strategyParameters, parameterValues);
    if (!paramsResult.ok) {
      setError(
        buildClientError({
          title: "Strategy parameters invalid",
          summary: paramsResult.error,
        })
      );
      return;
    }

    setCreatingRun(true);
    setInitializingRun(false);
    setInitializationError(null);
    setCreatedRunId("");
    setInitializationStatus({
      state: "CREATED",
      percent: 0,
      lastEvent: null,
    });
    setError(null);
    setInfo("Creating run...");
    const result = await createProductRun({
      dataset_id: datasetId,
      strategy_id: strategyId,
      params: paramsResult.value,
      risk_level: riskLevel,
    });
    if (!result.ok) {
      setCreatingRun(false);
      setInfo(null);
      setError(mapApiErrorDetails(result, "Run creation failed"));
      return;
    }

    const runId = String(result.data?.run_id || "");
    if (!runId) {
      setCreatingRun(false);
      setInfo(null);
      setError(
        buildClientError({
          title: "Run creation failed",
          summary: "Server response did not include run id.",
        })
      );
      return;
    }

    setCreatingRun(false);
    setCreatedRunId(runId);
    setInitializingRun(true);
    setStep(STEP_RUN);
    setInfo(`Run created: ${runId}. Initializing...`);
  };

  const handleDrop = (event) => {
    event.preventDefault();
    setDragActive(false);
    const file = event.dataTransfer?.files?.[0] || null;
    onFilePicked(file);
  };

  const handleDragOver = (event) => {
    event.preventDefault();
    setDragActive(true);
  };

  const handleDragLeave = (event) => {
    event.preventDefault();
    setDragActive(false);
  };

  const jumpToStep = (target) => {
    if (target === STEP_IMPORT) {
      setStep(target);
      return;
    }
    if (target === STEP_STRATEGY && canProceedToStrategy) {
      setStep(target);
      return;
    }
    if (target === STEP_CONFIGURE && canProceedToConfigure) {
      setStep(target);
      return;
    }
    if (target === STEP_RUN && canCreateRun) {
      setStep(target);
    }
  };

  return (
    <main>
      <header>
        <div className="header-title">
          <h1>Create Run</h1>
          <span>Import data, choose strategy, configure, and run.</span>
        </div>
        <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
          <Link className="badge info" href="/runs">
            Back to Runs
          </Link>
        </div>
      </header>

      <section className="card fade-up" style={{ marginBottom: "16px" }}>
        <div className="section-title">
          <h3>Wizard Steps</h3>
          <span className="muted">Follow in order</span>
        </div>
        <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
          <button className={stepClass(step, STEP_IMPORT)} onClick={() => jumpToStep(STEP_IMPORT)}>
            1. Import Data
          </button>
          <button
            className={stepClass(step, STEP_STRATEGY)}
            onClick={() => jumpToStep(STEP_STRATEGY)}
            disabled={!canProceedToStrategy}
          >
            2. Choose Strategy
          </button>
          <button
            className={stepClass(step, STEP_CONFIGURE)}
            onClick={() => jumpToStep(STEP_CONFIGURE)}
            disabled={!canProceedToConfigure}
          >
            3. Configure
          </button>
          <button
            className={stepClass(step, STEP_RUN)}
            onClick={() => jumpToStep(STEP_RUN)}
            disabled={!canCreateRun}
          >
            4. Run
          </button>
        </div>
      </section>

      {error && <ErrorNotice error={error} mode="pro" />}
      {info && <div className="card fade-up">{info}</div>}

      {loadingInitial ? (
        <div className="card fade-up">Loading strategies and imports...</div>
      ) : (
        <>
          {step === STEP_IMPORT && (
            <section className="card fade-up" data-testid="create-run-step-import">
              <div className="section-title">
                <h3>Step 1: Import Data</h3>
                <span className="muted">Upload a CSV file</span>
              </div>
              <input
                ref={hiddenFileInput}
                type="file"
                accept=".csv,text/csv"
                style={{ display: "none" }}
                onChange={(event) => onFilePicked(event.target?.files?.[0] || null)}
              />
              <div
                className="upload-dropzone"
                data-active={dragActive ? "true" : "false"}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                <div>Drag and drop your CSV here.</div>
                <div className="muted" style={{ fontSize: "0.85rem", marginTop: "6px" }}>
                  Required columns: timestamp, open, high, low, close, volume
                </div>
                <div style={{ marginTop: "12px", display: "flex", gap: "8px", flexWrap: "wrap" }}>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => hiddenFileInput.current?.click()}
                  >
                    Choose CSV
                  </button>
                  <button type="button" onClick={handleImportData} disabled={importing}>
                    {importing ? "Importing..." : "Import Data"}
                  </button>
                </div>
                <div className="muted" style={{ marginTop: "10px" }}>
                  {selectedFile ? `Selected file: ${selectedFile.name}` : "No file selected"}
                </div>
              </div>

              {selectedDataset && (
                <div className="card soft" style={{ marginTop: "16px" }}>
                  <div className="section-title">
                    <h3>Imported Dataset</h3>
                    <span className="badge ok">{selectedDataset.content_hash.slice(0, 12)}...</span>
                  </div>
                  <div className="grid two">
                    <div className="kpi">
                      <span>Filename</span>
                      <strong>{selectedDataset.filename}</strong>
                    </div>
                    <div className="kpi">
                      <span>Rows</span>
                      <strong>{selectedDataset.row_count}</strong>
                    </div>
                    <div className="kpi">
                      <span>Columns</span>
                      <strong>
                        {selectedDataset.columns.length > 0
                          ? selectedDataset.columns.join(", ")
                          : "n/a"}
                      </strong>
                    </div>
                    <div className="kpi">
                      <span>Time Range</span>
                      <strong>{formatTimeRange(selectedDataset.inferred_time_range)}</strong>
                    </div>
                  </div>
                  <div style={{ marginTop: "14px" }}>
                    <button type="button" onClick={() => setStep(STEP_STRATEGY)}>
                      Continue to Strategy
                    </button>
                  </div>
                </div>
              )}

              {datasets.length > 0 && (
                <div className="card soft" style={{ marginTop: "16px" }}>
                  <div className="section-title">
                    <h3>Or Use Existing Import</h3>
                    <span className="muted">{datasets.length} datasets</span>
                  </div>
                  <div className="grid two">
                    {datasets.map((dataset) => (
                      <button
                        key={dataset.content_hash}
                        type="button"
                        className="secondary"
                        style={{ textAlign: "left" }}
                        onClick={() => selectDataset(dataset)}
                      >
                        <strong>{dataset.content_hash.slice(0, 12)}...</strong>
                        <div className="muted">{dataset.filename}</div>
                        <div className="muted">{dataset.row_count} rows</div>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </section>
          )}

          {step === STEP_STRATEGY && (
            <section className="card fade-up" data-testid="create-run-step-strategy">
              <div className="section-title">
                <h3>Step 2: Choose Strategy</h3>
                <span className="muted">{strategies.length} available</span>
              </div>
              {strategies.length === 0 ? (
                <div className="banner">No strategies available. Check API strategy catalog.</div>
              ) : (
                <div className="grid two">
                  {strategies.map((strategy) => (
                    <button
                      key={strategy.id}
                      type="button"
                      className={
                        strategyId === strategy.id ? "selector-card selected" : "selector-card"
                      }
                      style={{ textAlign: "left" }}
                      onClick={() => {
                        setStrategyId(strategy.id);
                        setError(null);
                        setInfo(`Selected strategy: ${strategy.display_name}`);
                      }}
                    >
                      <strong>{strategy.display_name}</strong>
                      <div className="muted">{strategy.id}</div>
                      <div className="muted" style={{ marginTop: "8px" }}>
                        {strategy.description || "No description"}
                      </div>
                    </button>
                  ))}
                </div>
              )}
              <div style={{ marginTop: "16px", display: "flex", gap: "10px" }}>
                <button type="button" className="secondary" onClick={() => setStep(STEP_IMPORT)}>
                  Back
                </button>
                <button
                  type="button"
                  onClick={() => setStep(STEP_CONFIGURE)}
                  disabled={!canProceedToConfigure}
                >
                  Continue to Configure
                </button>
              </div>
            </section>
          )}

          {step === STEP_CONFIGURE && (
            <section className="card fade-up" data-testid="create-run-step-configure">
              <div className="section-title">
                <h3>Step 3: Configure</h3>
                <span className="muted">{selectedStrategy?.display_name || "No strategy selected"}</span>
              </div>

              <div className="grid two">
                <label>
                  Risk Level
                  <select
                    value={riskLevel}
                    onChange={(event) => setRiskLevel(Number(event.target.value))}
                  >
                    {RISK_LEVEL_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label} ({option.value})
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div style={{ marginTop: "16px" }}>
                <div className="section-title">
                  <h3>Strategy Parameters</h3>
                  <span className="muted">Rendered from strategy schema</span>
                </div>
                {strategyParameters.length === 0 ? (
                  <div className="card soft">This strategy has no configurable parameters.</div>
                ) : (
                  <div className="grid two">
                    {strategyParameters.map((parameter) => {
                      const value = parameterValues[parameter.name];
                      const schema = parameter.schema;
                      const type = parameter.type;
                      const enumValues = Array.isArray(schema.enum) ? schema.enum : [];

                      if (PARAM_BOOLEAN_TYPES.has(type)) {
                        return (
                          <label key={parameter.name}>
                            {parameter.name}
                            <input
                              type="checkbox"
                              checked={Boolean(value)}
                              onChange={(event) =>
                                setParameterValues((current) => ({
                                  ...current,
                                  [parameter.name]: event.target.checked,
                                }))
                              }
                            />
                          </label>
                        );
                      }

                      if (enumValues.length > 0) {
                        return (
                          <label key={parameter.name}>
                            {parameter.name}
                            <select
                              value={value ?? ""}
                              onChange={(event) =>
                                setParameterValues((current) => ({
                                  ...current,
                                  [parameter.name]: event.target.value,
                                }))
                              }
                            >
                              <option value="">Select value</option>
                              {enumValues.map((option) => (
                                <option key={option} value={option}>
                                  {option}
                                </option>
                              ))}
                            </select>
                          </label>
                        );
                      }

                      const isInteger = PARAM_INTEGER_TYPES.has(type);
                      const isNumber = isInteger || PARAM_NUMBER_TYPES.has(type);
                      return (
                        <label key={parameter.name}>
                          {parameter.name}
                          <input
                            type={isNumber ? "number" : "text"}
                            step={isInteger ? "1" : "0.01"}
                            min={Number.isFinite(schema.minimum) ? schema.minimum : undefined}
                            max={Number.isFinite(schema.maximum) ? schema.maximum : undefined}
                            value={value ?? ""}
                            onChange={(event) =>
                              setParameterValues((current) => ({
                                ...current,
                                [parameter.name]: event.target.value,
                              }))
                            }
                          />
                          {schema.description && (
                            <span className="muted" style={{ fontSize: "0.8rem" }}>
                              {schema.description}
                            </span>
                          )}
                        </label>
                      );
                    })}
                  </div>
                )}
              </div>

              <div style={{ marginTop: "16px", display: "flex", gap: "10px" }}>
                <button type="button" className="secondary" onClick={() => setStep(STEP_STRATEGY)}>
                  Back
                </button>
                <button type="button" onClick={() => setStep(STEP_RUN)}>
                  Continue to Run
                </button>
              </div>
            </section>
          )}

          {step === STEP_RUN && (
            <section className="card fade-up" data-testid="create-run-step-run">
              <div className="section-title">
                <h3>Step 4: Create Run</h3>
                <span className="muted">Start deterministic simulation</span>
              </div>
              <div className="grid two">
                <div className="kpi">
                  <span>Dataset</span>
                  <strong>{datasetId || "n/a"}</strong>
                </div>
                <div className="kpi">
                  <span>Strategy</span>
                  <strong>{strategyId || "n/a"}</strong>
                </div>
                <div className="kpi">
                  <span>Risk Level</span>
                  <strong>{riskLevel}</strong>
                </div>
                <div className="kpi">
                  <span>Run ID</span>
                  <strong>{createdRunId || "pending"}</strong>
                </div>
              </div>
              {initializingRun && (
                <div className="card soft" style={{ marginTop: "14px" }}>
                  <div className="section-title">
                    <h3>Run Initializing</h3>
                    <span className={`badge ${initializationBadgeKind(initializationStatus.state)}`}>
                      {initializationStatus.state}
                    </span>
                  </div>
                  <div className="grid two">
                    <div className="kpi">
                      <span>Progress</span>
                      <strong>{initializationStatus.percent}%</strong>
                    </div>
                    <div className="kpi">
                      <span>Last Event</span>
                      <strong>{initializationStatus.lastEvent?.stage || "n/a"}</strong>
                    </div>
                  </div>
                  <div className="muted" style={{ marginTop: "8px" }}>
                    Waiting for lifecycle transition before opening the workspace.
                  </div>
                </div>
              )}
              {initializationError && (
                <div style={{ marginTop: "14px" }}>
                  <ErrorNotice error={initializationError} compact />
                </div>
              )}
              <div style={{ marginTop: "16px", display: "flex", gap: "10px" }}>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setStep(STEP_CONFIGURE)}
                  disabled={creatingRun || initializingRun}
                >
                  Back
                </button>
                <button
                  type="button"
                  onClick={handleCreateRun}
                  disabled={creatingRun || initializingRun || !canCreateRun}
                >
                  {creatingRun ? "Creating..." : initializingRun ? "Initializing..." : "Create Run"}
                </button>
              </div>
            </section>
          )}
        </>
      )}
    </main>
  );
}

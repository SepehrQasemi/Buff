import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useMemo, useRef, useState } from "react";
import { buildApiUrl, createRun, getActivePlugins } from "../../lib/api";
import ErrorNotice from "../../components/ErrorNotice";
import { mapApiErrorDetails } from "../../lib/errorMapping";

const DEFAULT_PAYLOAD = {
  schema_version: "1.0.0",
  data_source: {
    type: "csv",
    path: "",
    symbol: "",
    timeframe: "1m",
    start_ts: "",
    end_ts: "",
  },
  strategy: {
    id: "",
    params: {},
  },
  risk: {
    level: 3,
  },
  costs: {
    commission_bps: 0,
    slippage_bps: 0,
  },
  run_id: "",
};

const TIMEFRAMES = ["1m", "5m"];
const RISK_LEVELS = [1, 2, 3, 4, 5];

const normalizeParams = (params) =>
  Array.isArray(params) ? params.filter((param) => param && param.name) : [];

const buildParamDefaults = (params) => {
  const defaults = {};
  normalizeParams(params).forEach((param) => {
    if (param.default !== undefined) {
      defaults[param.name] = param.default;
    }
  });
  return defaults;
};

const coerceParamValue = (param, value, fallback) => {
  if (!param) {
    return value;
  }
  const type = String(param.type || "").toLowerCase();
  if (type === "bool" || type === "boolean") {
    return Boolean(value);
  }
  if (type === "int" || type === "integer") {
    if (value === "") {
      return value;
    }
    const parsed = Number.parseInt(value, 10);
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  if (type === "float" || type === "number") {
    if (value === "") {
      return value;
    }
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  return value;
};

export default function RunsNewPage() {
  const router = useRouter();
  const [form, setForm] = useState(DEFAULT_PAYLOAD);
  const [strategies, setStrategies] = useState([]);
  const [loadingStrategies, setLoadingStrategies] = useState(true);
  const [submitState, setSubmitState] = useState("idle");
  const [reloadToken, setReloadToken] = useState(0);
  const [error, setError] = useState(null);
  const [info, setInfo] = useState(null);
  const [uploadFile, setUploadFile] = useState(null);
  const pluginsUrl = buildApiUrl("/plugins/active");
  const selectedStrategy = useMemo(
    () => strategies.find((strategy) => strategy.id === form.strategy.id) || null,
    [form.strategy.id, strategies]
  );
  const strategyParams = useMemo(
    () => normalizeParams(selectedStrategy?.schema?.params),
    [selectedStrategy]
  );
  const lastStrategyIdRef = useRef("");

  useEffect(() => {
    let active = true;
    async function loadStrategies() {
      setLoadingStrategies(true);
      const result = await getActivePlugins();
      if (!active) {
        return;
      }
      if (!result.ok) {
        setError(mapApiErrorDetails(result, "Failed to load active strategies"));
        setStrategies([]);
        setLoadingStrategies(false);
        return;
      }
      setError(null);
      const data = result.data || {};
      const items = Array.isArray(data.strategies) ? data.strategies : [];
      setStrategies(items);
      setLoadingStrategies(false);
    }
    loadStrategies();
    return () => {
      active = false;
    };
  }, [pluginsUrl, reloadToken]);

  useEffect(() => {
    const currentId = form.strategy.id;
    if (lastStrategyIdRef.current === currentId) {
      return;
    }
    lastStrategyIdRef.current = currentId;
    const defaults = buildParamDefaults(strategyParams);
    setForm((current) => ({
      ...current,
      strategy: { ...current.strategy, params: defaults },
    }));
  }, [form.strategy.id, strategyParams]);

  const handleFileChange = (event) => {
    const file = event.target?.files?.[0] || null;
    setUploadFile(file);
    if (file) {
      setForm((current) => ({
        ...current,
        data_source: { ...current.data_source, path: "" },
      }));
    }
  };

  const canSubmit = useMemo(() => {
    if (submitState === "submitting") {
      return false;
    }
    const hasFile = Boolean(uploadFile);
    const hasPath = Boolean(form.data_source.path.trim());
    if (!hasFile && !hasPath) {
      return false;
    }
    if (!form.data_source.symbol.trim()) {
      return false;
    }
    if (!form.strategy.id.trim()) {
      return false;
    }
    if (!form.risk.level) {
      return false;
    }
    if (!TIMEFRAMES.includes(form.data_source.timeframe)) {
      return false;
    }
    return true;
  }, [form, submitState, uploadFile]);

  const handleChange = (keyPath) => (event) => {
    const value = event.target.value;
    setForm((current) => {
      const next = { ...current };
      if (keyPath === "data_source.path") {
        next.data_source = { ...next.data_source, path: value };
      } else if (keyPath === "data_source.symbol") {
        next.data_source = { ...next.data_source, symbol: value };
      } else if (keyPath === "data_source.timeframe") {
        next.data_source = { ...next.data_source, timeframe: value };
      } else if (keyPath === "data_source.start_ts") {
        next.data_source = { ...next.data_source, start_ts: value };
      } else if (keyPath === "data_source.end_ts") {
        next.data_source = { ...next.data_source, end_ts: value };
      } else if (keyPath === "strategy.id") {
        next.strategy = { ...next.strategy, id: value };
      } else if (keyPath === "risk.level") {
        next.risk = { ...next.risk, level: Number(value) };
      } else if (keyPath === "costs.commission_bps") {
        next.costs = { ...next.costs, commission_bps: Number(value) };
      } else if (keyPath === "costs.slippage_bps") {
        next.costs = { ...next.costs, slippage_bps: Number(value) };
      } else if (keyPath === "run_id") {
        next.run_id = value;
      }
      return next;
    });
  };

  const handleParamChange = (param) => (event) => {
    if (!param || !param.name) {
      return;
    }
    const isBool = ["bool", "boolean"].includes(String(param.type || "").toLowerCase());
    const rawValue = isBool ? event.target.checked : event.target.value;
    setForm((current) => {
      const currentParams = current.strategy.params || {};
      const nextValue = coerceParamValue(param, rawValue, currentParams[param.name]);
      return {
        ...current,
        strategy: {
          ...current.strategy,
          params: { ...currentParams, [param.name]: nextValue },
        },
      };
    });
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError(null);
    setInfo(null);

    if (!canSubmit) {
      setError("Fill in all required fields before creating a run.");
      return;
    }

    const rawParams = form.strategy.params || {};
    const cleanedParams = Object.fromEntries(
      Object.entries(rawParams).filter(
        ([, value]) => value !== "" && value !== null && value !== undefined
      )
    );

    const payload = {
      schema_version: form.schema_version,
      data_source: {
        type: "csv",
        path: form.data_source.path.trim(),
        symbol: form.data_source.symbol.trim().toUpperCase(),
        timeframe: form.data_source.timeframe,
      },
      strategy: {
        id: form.strategy.id.trim(),
        params: cleanedParams,
      },
      risk: {
        level: Number(form.risk.level),
      },
      costs: {
        commission_bps: Number(form.costs.commission_bps),
        slippage_bps: Number(form.costs.slippage_bps),
      },
    };

    if (form.data_source.start_ts.trim()) {
      payload.data_source.start_ts = form.data_source.start_ts.trim();
    }
    if (form.data_source.end_ts.trim()) {
      payload.data_source.end_ts = form.data_source.end_ts.trim();
    }
    if (form.run_id.trim()) {
      payload.run_id = form.run_id.trim();
    }

    setSubmitState("submitting");
    setInfo("Submitting run request...");
    const result = await createRun(payload, uploadFile);
    if (!result.ok) {
      setSubmitState("idle");
      setInfo(null);
      setError(mapApiErrorDetails(result, "Run creation failed"));
      return;
    }

    const runId = result.data?.run_id;
    if (!runId) {
      setSubmitState("idle");
      setInfo(null);
      setError("Run created but run_id missing from response.");
      return;
    }

    setInfo(`Run created: ${runId}. Redirecting...`);
    router.push(`/runs/${runId}`);
  };

  return (
    <main>
      <header>
        <div className="header-title">
          <h1>Create Run</h1>
          <span>Stage-4 create flow using CSV inputs.</span>
        </div>
        <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
          <Link className="badge info" href="/runs">
            Back to Runs
          </Link>
        </div>
      </header>

      <div className="banner info">
        Runs are stored under RUNS_ROOT on the API host. Upload a CSV file to create a
        run. A legacy repo-relative path input remains available as a temporary fallback.
      </div>

      <div className="card fade-up" style={{ marginBottom: "16px" }}>
        Active plugins endpoint: {pluginsUrl}
      </div>

      {error && <ErrorNotice error={error} onRetry={() => setReloadToken((v) => v + 1)} />}
      {info && <div className="card fade-up">{info}</div>}

      <form className="card fade-up" onSubmit={handleSubmit}>
        <div className="section-title">
          <h3>Run Inputs</h3>
          <span className="muted">All fields are validated server-side.</span>
        </div>

        <div className="grid two" style={{ marginTop: "16px" }}>
          <label>
            CSV File (upload)
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={handleFileChange}
            />
          </label>

          <label>
            CSV Path (legacy, repo-relative)
            <input
              type="text"
              placeholder="tests/fixtures/phase6/sample.csv"
              value={form.data_source.path}
              onChange={handleChange("data_source.path")}
            />
          </label>

          <label>
            Symbol
            <input
              type="text"
              placeholder="BTCUSDT"
              value={form.data_source.symbol}
              onChange={handleChange("data_source.symbol")}
              required
            />
          </label>

          <label>
            Timeframe
            <select
              value={form.data_source.timeframe}
              onChange={handleChange("data_source.timeframe")}
            >
              {TIMEFRAMES.map((frame) => (
                <option key={frame} value={frame}>
                  {frame}
                </option>
              ))}
            </select>
          </label>

          <label>
            Strategy
            <select
              value={form.strategy.id}
              onChange={handleChange("strategy.id")}
              required
              disabled={loadingStrategies || strategies.length === 0}
            >
              <option value="">Select a strategy</option>
              {strategies.map((strategy) => (
                <option key={strategy.id} value={strategy.id}>
                  {strategy.name ? `${strategy.name} (${strategy.id})` : strategy.id}
                </option>
              ))}
            </select>
          </label>

          <label>
            Risk Level
            <select value={form.risk.level} onChange={handleChange("risk.level")}>
              {RISK_LEVELS.map((level) => (
                <option key={level} value={level}>
                  {level}
                </option>
              ))}
            </select>
          </label>

          <label>
            Run ID (optional)
            <input
              type="text"
              placeholder="run_custom_id"
              value={form.run_id}
              onChange={handleChange("run_id")}
            />
          </label>

          <label>
            Start (UTC, optional)
            <input
              type="text"
              placeholder="2026-02-01T00:00:00Z"
              value={form.data_source.start_ts}
              onChange={handleChange("data_source.start_ts")}
            />
          </label>

          <label>
            End (UTC, optional)
            <input
              type="text"
              placeholder="2026-02-02T00:00:00Z"
              value={form.data_source.end_ts}
              onChange={handleChange("data_source.end_ts")}
            />
          </label>

          <label>
            Commission (bps)
            <input
              type="number"
              min="0"
              step="0.01"
              value={form.costs.commission_bps}
              onChange={handleChange("costs.commission_bps")}
            />
          </label>

          <label>
            Slippage (bps)
            <input
              type="number"
              min="0"
              step="0.01"
              value={form.costs.slippage_bps}
              onChange={handleChange("costs.slippage_bps")}
            />
          </label>
        </div>

        {form.strategy.id && (
          <div style={{ marginTop: "20px" }}>
            <div className="section-title">
              <h3>Strategy Parameters</h3>
              <span className="muted">Defaults are loaded from the plugin schema.</span>
            </div>
            {strategyParams.length === 0 ? (
              <div className="card" style={{ marginTop: "12px" }}>
                No parameters required for this strategy.
              </div>
            ) : (
              <div className="grid two" style={{ marginTop: "12px" }}>
                {strategyParams.map((param) => {
                  const paramType = String(param.type || "").toLowerCase();
                  const currentValue =
                    form.strategy.params?.[param.name] ?? param.default ?? "";
                  const isBool = ["bool", "boolean"].includes(paramType);
                  const isInt = ["int", "integer"].includes(paramType);
                  const isNumber = isInt || ["float", "number"].includes(paramType);
                  const inputProps = {};
                  if (Number.isFinite(param.min)) {
                    inputProps.min = param.min;
                  }
                  if (Number.isFinite(param.max)) {
                    inputProps.max = param.max;
                  }
                  if (isNumber) {
                    inputProps.step = isInt ? "1" : "0.01";
                  }
                  return (
                    <label key={param.name}>
                      {param.name}
                      {param.description && (
                        <span className="muted" style={{ display: "block" }}>
                          {param.description}
                        </span>
                      )}
                      {isBool ? (
                        <input
                          type="checkbox"
                          checked={Boolean(currentValue)}
                          onChange={handleParamChange(param)}
                        />
                      ) : (
                        <input
                          type={isNumber ? "number" : "text"}
                          value={currentValue}
                          onChange={handleParamChange(param)}
                          {...inputProps}
                        />
                      )}
                    </label>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {loadingStrategies ? (
          <div className="card" style={{ marginTop: "16px" }}>
            Loading strategies...
          </div>
        ) : strategies.length === 0 ? (
          <div className="card" style={{ marginTop: "16px" }}>
            No validated strategies found in /api/v1/plugins/active. Run plugin validation
            or fix the plugin registry before creating runs.
          </div>
        ) : null}

        <div style={{ display: "flex", gap: "12px", marginTop: "16px" }}>
          <button type="submit" disabled={!canSubmit}>
            {submitState === "submitting" ? "Creating..." : "Create Run"}
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setForm(DEFAULT_PAYLOAD);
              setUploadFile(null);
            }}
          >
            Reset
          </button>
        </div>
      </form>
    </main>
  );
}

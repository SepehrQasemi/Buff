import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useMemo, useState } from "react";
import AppShell from "../../components/AppShell";
import ErrorNotice from "../../components/ErrorNotice";
import { createExperiment, getExperimentsIndex, getStrategies } from "../../lib/api";
import { buildClientError, mapApiErrorDetails } from "../../lib/errorMapping";
import { buildRunParameters, getStrategyParameters } from "../../lib/runConfig";
import { useToast } from "../../lib/toast";

const EXPERIMENT_SCHEMA_VERSION = "1.0.0";
const RUN_SCHEMA_VERSION = "1.0.0";
const MIN_CANDIDATES = 2;
const MAX_CANDIDATES = 20;
const RECENT_EXPERIMENTS_STORAGE_KEY = "buff_recent_experiments";
const MAX_RECENT_EXPERIMENTS = 10;
const EXPERIMENT_ID_PATTERN = /^exp_[a-z0-9]+$/;

const PARAM_INTEGER_TYPES = new Set(["integer", "int"]);
const PARAM_NUMBER_TYPES = new Set(["number", "float"]);
const PARAM_BOOLEAN_TYPES = new Set(["boolean", "bool"]);

const isObject = (value) => Boolean(value) && typeof value === "object" && !Array.isArray(value);

const normalizeExperimentIdInput = (value) => String(value || "").trim().toLowerCase();

const isValidExperimentId = (value) => EXPERIMENT_ID_PATTERN.test(value);

const normalizeRecentExperimentIds = (value) => {
  if (!Array.isArray(value)) {
    return [];
  }
  const unique = [];
  value.forEach((item) => {
    const experimentId = normalizeExperimentIdInput(item);
    if (!experimentId || !isValidExperimentId(experimentId) || unique.includes(experimentId)) {
      return;
    }
    unique.push(experimentId);
  });
  return unique.slice(0, MAX_RECENT_EXPERIMENTS);
};

const upsertRecentExperimentId = (experimentId, current) => {
  const normalizedId = normalizeExperimentIdInput(experimentId);
  if (!normalizedId || !isValidExperimentId(normalizedId)) {
    return normalizeRecentExperimentIds(current);
  }
  return [
    normalizedId,
    ...normalizeRecentExperimentIds(current).filter((item) => item !== normalizedId),
  ].slice(0, MAX_RECENT_EXPERIMENTS);
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
  };
};

const buildCandidateId = (index) => `cand_${String(index + 1).padStart(3, "0")}`;

const defaultCandidate = (index, strategyId = "") => ({
  candidateId: buildCandidateId(index),
  label: "",
  strategyId,
  params: {},
});

const nextCandidateId = (candidates) => {
  const used = new Set(candidates.map((candidate) => candidate.candidateId));
  let index = 0;
  while (index < 999) {
    const candidateId = buildCandidateId(index);
    if (!used.has(candidateId)) {
      return candidateId;
    }
    index += 1;
  }
  return `cand_${String(candidates.length + 1).padStart(3, "0")}`;
};

const buildDefaultParams = (strategy) =>
  getStrategyParameters(strategy).reduce((acc, parameter) => {
    acc[parameter.name] = parameter.defaultValue;
    return acc;
  }, {});

const normalizeIndexEntry = (item) => {
  if (!isObject(item)) {
    return null;
  }
  const experimentId = normalizeExperimentIdInput(item.experiment_id);
  if (!experimentId) {
    return null;
  }
  const status = String(item.status || "BROKEN").trim().toUpperCase() || "BROKEN";
  const toCount = (value) => {
    if (typeof value === "number" && Number.isFinite(value)) {
      return Math.max(0, Math.trunc(value));
    }
    if (typeof value === "string") {
      const parsed = Number.parseInt(value, 10);
      if (Number.isFinite(parsed)) {
        return Math.max(0, parsed);
      }
    }
    return 0;
  };
  const createdAt = item.created_at === null || item.created_at === undefined ? null : String(item.created_at);
  return {
    experiment_id: experimentId,
    status,
    created_at: createdAt,
    succeeded_count: toCount(item.succeeded_count),
    failed_count: toCount(item.failed_count),
    total_candidates: toCount(item.total_candidates),
  };
};

const experimentStatusBadgeClass = (status) => {
  const normalized = String(status || "").toUpperCase();
  if (normalized === "COMPLETED" || normalized === "OK") {
    return "status-completed";
  }
  if (normalized === "PARTIAL") {
    return "status-partial";
  }
  if (normalized === "FAILED" || normalized === "BROKEN") {
    return "status-failed";
  }
  return "info";
};

export default function ExperimentsPage() {
  const router = useRouter();
  const { toast } = useToast();
  const [strategies, setStrategies] = useState([]);
  const [loadingStrategies, setLoadingStrategies] = useState(true);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [createdExperiment, setCreatedExperiment] = useState(null);
  const [openExperimentId, setOpenExperimentId] = useState("");
  const [recentExperiments, setRecentExperiments] = useState([]);
  const [copiedRecentId, setCopiedRecentId] = useState("");
  const [experimentsIndex, setExperimentsIndex] = useState([]);
  const [loadingExperimentsIndex, setLoadingExperimentsIndex] = useState(true);
  const [experimentsIndexError, setExperimentsIndexError] = useState(null);

  const [experimentName, setExperimentName] = useState("");
  const [runConfig, setRunConfig] = useState({
    path: "tests/fixtures/phase6/sample.csv",
    symbol: "BTCUSDT",
    timeframe: "1m",
    riskLevel: 3,
    commissionBps: 0.0,
    slippageBps: 0.0,
  });

  const [candidates, setCandidates] = useState(() => [defaultCandidate(0), defaultCandidate(1)]);

  const strategiesById = useMemo(() => {
    const byId = new Map();
    strategies.forEach((strategy) => byId.set(strategy.id, strategy));
    return byId;
  }, [strategies]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    try {
      const raw = window.localStorage.getItem(RECENT_EXPERIMENTS_STORAGE_KEY);
      if (!raw) {
        return;
      }
      const parsed = JSON.parse(raw);
      setRecentExperiments(normalizeRecentExperimentIds(parsed));
    } catch {
      setRecentExperiments([]);
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    try {
      window.localStorage.setItem(
        RECENT_EXPERIMENTS_STORAGE_KEY,
        JSON.stringify(normalizeRecentExperimentIds(recentExperiments))
      );
    } catch {
      // Local storage can be unavailable; keep runtime behavior non-fatal.
    }
  }, [recentExperiments]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoadingStrategies(true);
      const result = await getStrategies();
      if (!active) {
        return;
      }
      if (!result.ok) {
        setError(mapApiErrorDetails(result, "Failed to load strategies"));
        setStrategies([]);
        setLoadingStrategies(false);
        return;
      }
      const normalized = Array.isArray(result.data)
        ? result.data.map(normalizeStrategy).filter(Boolean)
        : [];
      setStrategies(normalized);
      if (normalized.length === 0) {
        setError(
          buildClientError({
            title: "No strategies available",
            summary: "Strategy catalog is empty. Check API plugin catalog and retry.",
          })
        );
      } else {
        setError(null);
      }
      setLoadingStrategies(false);
    };
    load();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoadingExperimentsIndex(true);
      const result = await getExperimentsIndex();
      if (!active) {
        return;
      }
      if (!result.ok) {
        setExperimentsIndex([]);
        setExperimentsIndexError(mapApiErrorDetails(result, "Failed to load experiments index"));
        setLoadingExperimentsIndex(false);
        return;
      }
      const normalized = Array.isArray(result.data)
        ? result.data.map(normalizeIndexEntry).filter(Boolean)
        : [];
      setExperimentsIndex(normalized);
      setExperimentsIndexError(null);
      setLoadingExperimentsIndex(false);
    };
    load();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (strategies.length === 0) {
      return;
    }
    setCandidates((current) =>
      current.map((candidate) => {
        const selectedStrategy =
          strategiesById.get(candidate.strategyId) || strategies[0] || null;
        if (!selectedStrategy) {
          return candidate;
        }
        const defaults = buildDefaultParams(selectedStrategy);
        return {
          ...candidate,
          strategyId: selectedStrategy.id,
          params:
            candidate.strategyId === selectedStrategy.id
              ? { ...defaults, ...(candidate.params || {}) }
              : defaults,
        };
      })
    );
  }, [strategies, strategiesById]);

  const updateCandidate = (index, updater) => {
    setCandidates((current) =>
      current.map((candidate, candidateIndex) =>
        candidateIndex === index ? updater(candidate) : candidate
      )
    );
  };

  const addCandidate = () => {
    setCandidates((current) => {
      if (current.length >= MAX_CANDIDATES) {
        return current;
      }
      const fallbackStrategy = strategies[0] || null;
      const next = {
        ...defaultCandidate(0, fallbackStrategy?.id || ""),
        candidateId: nextCandidateId(current),
      };
      if (fallbackStrategy) {
        next.params = buildDefaultParams(fallbackStrategy);
      }
      return [...current, next];
    });
  };

  const removeCandidate = (index) => {
    setCandidates((current) => {
      if (current.length <= MIN_CANDIDATES) {
        return current;
      }
      return current.filter((_, candidateIndex) => candidateIndex !== index);
    });
  };

  const addRecentExperiment = (experimentId) => {
    setRecentExperiments((current) => upsertRecentExperimentId(experimentId, current));
  };

  const removeRecentExperiment = (experimentId) => {
    setRecentExperiments((current) => current.filter((item) => item !== experimentId));
  };

  const clearRecentExperiments = () => {
    setRecentExperiments([]);
  };

  const copyRecentExperimentId = async (experimentId) => {
    if (typeof window === "undefined") {
      return;
    }
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(experimentId);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = experimentId;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        textarea.remove();
      }
      setCopiedRecentId(experimentId);
      toast({ title: "Copied", message: experimentId, kind: "info" });
      setTimeout(() => setCopiedRecentId(""), 1200);
    } catch {
      setCopiedRecentId("");
    }
  };

  const openExistingExperiment = () => {
    const experimentId = normalizeExperimentIdInput(openExperimentId);
    if (!experimentId) {
      toast({
        title: "Experiment id required",
        message: "Enter an experiment id before opening.",
        kind: "error",
      });
      setError(
        buildClientError({
          title: "Experiment id required",
          summary: "Enter an experiment id before opening.",
        })
      );
      return;
    }
    if (!isValidExperimentId(experimentId)) {
      toast({
        title: "Invalid experiment id",
        message: "Experiment ids must start with 'exp_'.",
        kind: "error",
      });
      setError(
        buildClientError({
          title: "Invalid experiment id",
          summary: "Experiment ids must start with 'exp_'.",
          actions: ["Use an id like exp_abcdef123456."],
        })
      );
      return;
    }
    setError(null);
    addRecentExperiment(experimentId);
    router.push(`/experiments/${experimentId}`);
  };

  const submitExperiment = async () => {
    setCreatedExperiment(null);
    if (candidates.length < MIN_CANDIDATES) {
      setError(
        buildClientError({
          title: "At least two candidates required",
          summary: "Add another candidate before submitting this experiment.",
        })
      );
      return;
    }
    if (candidates.length > MAX_CANDIDATES) {
      setError(
        buildClientError({
          title: "Too many candidates",
          summary: `This request has ${candidates.length} candidates and exceeds cap ${MAX_CANDIDATES}.`,
          actions: ["Reduce candidate count or split into multiple experiments."],
        })
      );
      return;
    }
    if (!runConfig.path.trim()) {
      setError(
        buildClientError({
          title: "Data path required",
          summary: "Enter a CSV path before running the experiment.",
        })
      );
      return;
    }

    const normalizedCandidates = [];
    for (let index = 0; index < candidates.length; index += 1) {
      const candidate = candidates[index];
      const strategy = strategiesById.get(candidate.strategyId);
      if (!strategy) {
        setError(
          buildClientError({
            title: "Strategy required",
            summary: `Select a strategy for candidate ${index + 1}.`,
          })
        );
        return;
      }
      const parameterSchema = getStrategyParameters(strategy);
      const paramsResult = buildRunParameters(parameterSchema, candidate.params || {});
      if (!paramsResult.ok) {
        setError(
          buildClientError({
            title: "Candidate parameters invalid",
            summary: `Candidate ${candidate.candidateId}: ${paramsResult.error}`,
          })
        );
        return;
      }

      normalizedCandidates.push({
        candidate_id: candidate.candidateId,
        ...(candidate.label.trim() ? { label: candidate.label.trim() } : {}),
        run_config: {
          schema_version: RUN_SCHEMA_VERSION,
          data_source: {
            type: "csv",
            path: runConfig.path.trim(),
            symbol: String(runConfig.symbol || "").trim().toUpperCase(),
            timeframe: String(runConfig.timeframe || "").trim(),
          },
          strategy: {
            id: strategy.id,
            params: paramsResult.value,
          },
          risk: {
            level: Number.parseInt(String(runConfig.riskLevel), 10),
          },
          costs: {
            commission_bps: Number.parseFloat(String(runConfig.commissionBps)),
            slippage_bps: Number.parseFloat(String(runConfig.slippageBps)),
          },
        },
      });
    }

    const payload = {
      schema_version: EXPERIMENT_SCHEMA_VERSION,
      candidates: normalizedCandidates,
      ...(experimentName.trim() ? { name: experimentName.trim() } : {}),
    };

    setSubmitting(true);
    const result = await createExperiment(payload);
    setSubmitting(false);

    if (!result.ok) {
      setError(mapApiErrorDetails(result, "Failed to create experiment"));
      return;
    }

    const experimentId = normalizeExperimentIdInput(result.data?.experiment_id);
    if (experimentId) {
      addRecentExperiment(experimentId);
      toast({
        title: "Experiment submitted",
        message: experimentId,
        kind: "success",
      });
    }
    setError(null);
    setCreatedExperiment(result.data);
  };

  return (
    <AppShell>
      <main>
        <header>
          <div className="header-title">
            <h1>Experiments</h1>
            <span>SIM_ONLY orchestration from artifact-backed run candidates.</span>
          </div>
          <Link className="badge info" href="/runs">
            Back to Runs
          </Link>
        </header>

        {error && <ErrorNotice error={error} mode="pro" />}

        <section className="card fade-up" style={{ marginBottom: "16px" }}>
          <div className="section-title">
            <h3>Open Existing Experiment</h3>
            <span className="badge info">{recentExperiments.length} recent</span>
          </div>
          <div className="grid two">
            <label>
              Experiment ID
              <input
                type="text"
                value={openExperimentId}
                onChange={(event) => setOpenExperimentId(event.target.value)}
                placeholder="exp_abcdef123456"
              />
            </label>
            <div style={{ display: "flex", gap: "10px", alignItems: "flex-end", flexWrap: "wrap" }}>
              <button type="button" onClick={openExistingExperiment}>
                Open
              </button>
            </div>
          </div>

          <div style={{ marginTop: "14px" }}>
            <div className="section-title">
              <h3>Recent Experiments</h3>
              {recentExperiments.length > 0 && (
                <button type="button" className="secondary" onClick={clearRecentExperiments}>
                  Clear All
                </button>
              )}
            </div>
            {recentExperiments.length === 0 ? (
              <p className="muted" style={{ margin: 0 }}>
                No recent experiments yet.
              </p>
            ) : (
              <div className="grid" style={{ gap: "8px" }}>
                {recentExperiments.map((experimentId) => (
                  <div
                    key={experimentId}
                    style={{
                      display: "flex",
                      gap: "10px",
                      alignItems: "center",
                      justifyContent: "space-between",
                      flexWrap: "wrap",
                    }}
                  >
                    <Link href={`/experiments/${experimentId}`}>{experimentId}</Link>
                    <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => copyRecentExperimentId(experimentId)}
                      >
                        {copiedRecentId === experimentId ? "Copied" : "Copy"}
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => removeRecentExperiment(experimentId)}
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>

        <section className="card fade-up" style={{ marginBottom: "16px" }}>
          <div className="section-title">
            <h3>Experiments (latest)</h3>
            <span className="badge info">{experimentsIndex.length}</span>
          </div>
          {experimentsIndexError && <ErrorNotice error={experimentsIndexError} compact mode="pro" />}
          {loadingExperimentsIndex ? (
            <div className="skeleton-stack" aria-label="Loading experiments index">
              <div className="skeleton-line" />
              <div className="skeleton-line medium" />
              <div className="skeleton-line short" />
            </div>
          ) : experimentsIndex.length === 0 ? (
            <div className="empty-state">
              <p>No experiment artifacts found for this user.</p>
            </div>
          ) : (
            <div className="table-wrap" style={{ maxHeight: "280px" }}>
              <table>
                <thead>
                  <tr>
                    <th>Experiment</th>
                    <th>Status</th>
                    <th>Succeeded</th>
                    <th>Failed</th>
                    <th>Total</th>
                    <th>Created</th>
                    <th>Open</th>
                  </tr>
                </thead>
                <tbody>
                  {experimentsIndex.map((item) => (
                    <tr key={item.experiment_id}>
                      <td>{item.experiment_id}</td>
                      <td>
                        <span className={`badge ${experimentStatusBadgeClass(item.status)}`}>
                          {item.status}
                        </span>
                      </td>
                      <td>{item.succeeded_count}</td>
                      <td>{item.failed_count}</td>
                      <td>{item.total_candidates}</td>
                      <td>{item.created_at || "n/a"}</td>
                      <td>
                        <Link href={`/experiments/${item.experiment_id}`}>Open</Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {createdExperiment && (
          <section className="card fade-up" style={{ marginBottom: "16px" }}>
            <div className="section-title">
              <h3>Experiment Submitted</h3>
              <span
                className={`badge ${experimentStatusBadgeClass(createdExperiment.status || "COMPLETED")}`}
              >
                {createdExperiment.status || "COMPLETED"}
              </span>
            </div>
            <div className="grid three">
              <div className="kpi">
                <span>Experiment ID</span>
                <strong>{createdExperiment.experiment_id || "n/a"}</strong>
              </div>
              <div className="kpi">
                <span>Succeeded</span>
                <strong>{createdExperiment.counts?.succeeded ?? "n/a"}</strong>
              </div>
              <div className="kpi">
                <span>Failed</span>
                <strong>{createdExperiment.counts?.failed ?? "n/a"}</strong>
              </div>
            </div>
            {createdExperiment.experiment_id && (
              <div style={{ marginTop: "12px", display: "flex", gap: "10px", flexWrap: "wrap" }}>
                <Link href={`/experiments/${createdExperiment.experiment_id}`}>
                  <button type="button">Open Experiment Detail</button>
                </Link>
              </div>
            )}
          </section>
        )}

        <section className="card fade-up" style={{ marginBottom: "16px" }}>
          <div className="section-title">
            <h3>Experiment Definition</h3>
            <span className="badge info">
              {candidates.length}/{MAX_CANDIDATES} candidates
            </span>
          </div>
          <p className="muted" style={{ marginTop: 0 }}>
            Experiments run candidate SIM_ONLY configs sequentially and compare results from
            generated artifacts only.
          </p>
          <div className="grid two" style={{ marginTop: "12px" }}>
            <label>
              Experiment Name (optional)
              <input
                type="text"
                value={experimentName}
                onChange={(event) => setExperimentName(event.target.value)}
                placeholder="s7-comparison"
              />
            </label>
            <div />
            <label>
              CSV Path
              <input
                type="text"
                value={runConfig.path}
                onChange={(event) =>
                  setRunConfig((current) => ({ ...current, path: event.target.value }))
                }
                placeholder="tests/fixtures/phase6/sample.csv"
              />
            </label>
            <label>
              Symbol
              <input
                type="text"
                value={runConfig.symbol}
                onChange={(event) =>
                  setRunConfig((current) => ({ ...current, symbol: event.target.value }))
                }
                placeholder="BTCUSDT"
              />
            </label>
            <label>
              Timeframe
              <input
                type="text"
                value={runConfig.timeframe}
                onChange={(event) =>
                  setRunConfig((current) => ({ ...current, timeframe: event.target.value }))
                }
                placeholder="1m"
              />
            </label>
            <label>
              Risk Level
              <input
                type="number"
                min="1"
                value={runConfig.riskLevel}
                onChange={(event) =>
                  setRunConfig((current) => ({
                    ...current,
                    riskLevel: event.target.value,
                  }))
                }
              />
            </label>
            <label>
              Commission (bps)
              <input
                type="number"
                step="0.01"
                value={runConfig.commissionBps}
                onChange={(event) =>
                  setRunConfig((current) => ({
                    ...current,
                    commissionBps: event.target.value,
                  }))
                }
              />
            </label>
            <label>
              Slippage (bps)
              <input
                type="number"
                step="0.01"
                value={runConfig.slippageBps}
                onChange={(event) =>
                  setRunConfig((current) => ({
                    ...current,
                    slippageBps: event.target.value,
                  }))
                }
              />
            </label>
          </div>
        </section>

        <section className="card fade-up">
          <div className="section-title">
            <h3>Candidates</h3>
            <button
              type="button"
              className="secondary"
              onClick={addCandidate}
              disabled={candidates.length >= MAX_CANDIDATES}
            >
              Add Candidate
            </button>
          </div>

          {loadingStrategies ? (
            <div className="skeleton-stack" aria-label="Loading strategy catalog">
              <div className="skeleton-line" />
              <div className="skeleton-line medium" />
              <div className="skeleton-line short" />
            </div>
          ) : (
            <div className="grid" style={{ gap: "14px" }}>
              {candidates.map((candidate, index) => {
                const selectedStrategy = strategiesById.get(candidate.strategyId) || null;
                const parameterSchema = selectedStrategy
                  ? getStrategyParameters(selectedStrategy)
                  : [];

                return (
                  <article key={candidate.candidateId} className="card soft">
                    <div className="section-title">
                      <h3>{candidate.candidateId}</h3>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => removeCandidate(index)}
                        disabled={candidates.length <= MIN_CANDIDATES}
                      >
                        Remove
                      </button>
                    </div>

                    <div className="grid two">
                      <label>
                        Label (optional)
                        <input
                          type="text"
                          value={candidate.label}
                          onChange={(event) =>
                            updateCandidate(index, (current) => ({
                              ...current,
                              label: event.target.value,
                            }))
                          }
                          placeholder={`Candidate ${index + 1}`}
                        />
                      </label>
                      <label>
                        Strategy
                        <select
                          value={candidate.strategyId}
                          onChange={(event) => {
                            const nextStrategyId = event.target.value;
                            const nextStrategy = strategiesById.get(nextStrategyId);
                            updateCandidate(index, (current) => ({
                              ...current,
                              strategyId: nextStrategyId,
                              params: nextStrategy ? buildDefaultParams(nextStrategy) : {},
                            }));
                          }}
                        >
                          {strategies.map((strategy) => (
                            <option key={strategy.id} value={strategy.id}>
                              {strategy.display_name}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>

                    {selectedStrategy?.description && (
                      <p className="muted" style={{ marginTop: "12px", marginBottom: 0 }}>
                        {selectedStrategy.description}
                      </p>
                    )}

                    <div style={{ marginTop: "14px" }}>
                      <div className="section-title">
                        <h3>Parameters</h3>
                      </div>
                      {parameterSchema.length === 0 ? (
                        <p className="muted" style={{ margin: 0 }}>
                          This strategy has no configurable parameters.
                        </p>
                      ) : (
                        <div className="grid two">
                          {parameterSchema.map((parameter) => {
                            const value = candidate.params?.[parameter.name];
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
                                      updateCandidate(index, (current) => ({
                                        ...current,
                                        params: {
                                          ...(current.params || {}),
                                          [parameter.name]: event.target.checked,
                                        },
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
                                      updateCandidate(index, (current) => ({
                                        ...current,
                                        params: {
                                          ...(current.params || {}),
                                          [parameter.name]: event.target.value,
                                        },
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
                                    updateCandidate(index, (current) => ({
                                      ...current,
                                      params: {
                                        ...(current.params || {}),
                                        [parameter.name]: event.target.value,
                                      },
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
                  </article>
                );
              })}
            </div>
          )}

          <div style={{ marginTop: "16px", display: "flex", gap: "10px", flexWrap: "wrap" }}>
            <button
              type="button"
              onClick={submitExperiment}
              disabled={submitting || loadingStrategies || strategies.length === 0}
            >
              {submitting ? "Running..." : "Run Experiment"}
            </button>
          </div>
        </section>
      </main>
    </AppShell>
  );
}

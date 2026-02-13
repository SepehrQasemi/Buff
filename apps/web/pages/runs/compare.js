import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useMemo, useRef, useState } from "react";
import CandlestickChart from "../../components/workspace/CandlestickChart";
import { getMetrics, getOhlcv, getRunSummary, getRuns, getTradeMarkers } from "../../lib/api";
import { formatApiError } from "../../lib/errors";

const formatValue = (value) => {
  if (value === null || value === undefined || value === "") {
    return "n/a";
  }
  return String(value);
};

const formatList = (value) => {
  if (Array.isArray(value)) {
    return value.length > 0 ? value.join(", ") : "n/a";
  }
  return formatValue(value);
};

const normalizeParam = (value) => {
  if (Array.isArray(value)) {
    return value[0];
  }
  return value;
};

const buildArtifactList = (artifacts) => {
  if (!artifacts) {
    return "n/a";
  }
  const entries = Object.entries(artifacts)
    .filter(([, value]) => value)
    .map(([key]) => key);
  return entries.length > 0 ? entries.join(", ") : "n/a";
};

const buildSummaryRange = (summary) => {
  if (!summary) {
    return "n/a";
  }
  const start = summary.min_timestamp;
  const end = summary.max_timestamp;
  if (!start && !end) {
    return "n/a";
  }
  return `${start || "n/a"} -> ${end || "n/a"}`;
};

const buildMetadataRows = ({ runId, runMeta, summary }) => {
  const provenance = summary?.provenance || {};
  return [
    { label: "Run ID", value: formatValue(summary?.run_id || runMeta?.id || runId) },
    {
      label: "Strategy",
      value: formatValue(
        runMeta?.strategy ||
          provenance.strategy_id ||
          provenance.strategy_name ||
          provenance.strategy
      ),
    },
    {
      label: "Strategy Version",
      value: formatValue(provenance.strategy_version),
    },
    {
      label: "Symbols",
      value: formatList(runMeta?.symbols || provenance.symbols),
    },
    {
      label: "Timeframe",
      value: formatValue(runMeta?.timeframe || provenance.timeframe),
    },
    {
      label: "Created",
      value: formatValue(runMeta?.created_at),
    },
    {
      label: "Decision Range",
      value: buildSummaryRange(summary),
    },
    {
      label: "Artifacts",
      value: buildArtifactList(summary?.artifacts),
    },
  ];
};

const RUN_MARKER_STYLES = {
  runA: { entry: "var(--accent)", exit: "var(--accent-2)" },
  runB: { entry: "var(--chart-up)", exit: "var(--chart-down)" },
};

const isScalarMetric = (value) =>
  value === null ||
  value === undefined ||
  ["string", "number", "boolean"].includes(typeof value);

const collectMetricKeys = (metrics) => {
  if (!metrics || typeof metrics !== "object") {
    return [];
  }
  return Object.entries(metrics)
    .filter(([, value]) => isScalarMetric(value))
    .map(([key]) => key);
};

const normalizeSymbolKey = (value) => {
  if (!value) {
    return "";
  }
  if (Array.isArray(value)) {
    return value.slice().sort().join("|");
  }
  return String(value);
};

export default function CompareRunsPage() {
  const router = useRouter();
  const runAId = normalizeParam(router.query.runA);
  const runBId = normalizeParam(router.query.runB);

  const [runsIndex, setRunsIndex] = useState([]);
  const [runsError, setRunsError] = useState(null);
  const [summaryA, setSummaryA] = useState(null);
  const [summaryB, setSummaryB] = useState(null);
  const [summaryErrorA, setSummaryErrorA] = useState(null);
  const [summaryErrorB, setSummaryErrorB] = useState(null);
  const [metricsA, setMetricsA] = useState(null);
  const [metricsB, setMetricsB] = useState(null);
  const [metricsErrorA, setMetricsErrorA] = useState(null);
  const [metricsErrorB, setMetricsErrorB] = useState(null);
  const [markersA, setMarkersA] = useState([]);
  const [markersB, setMarkersB] = useState([]);
  const [markersErrorA, setMarkersErrorA] = useState(null);
  const [markersErrorB, setMarkersErrorB] = useState(null);
  const [ohlcv, setOhlcv] = useState(null);
  const [ohlcvError, setOhlcvError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showRunAMarkers, setShowRunAMarkers] = useState(true);
  const [showRunBMarkers, setShowRunBMarkers] = useState(true);

  const requestIdRef = useRef(0);
  const abortRef = useRef(null);

  useEffect(() => {
    if (!router.isReady) {
      return;
    }
    if (!runAId || !runBId || runAId === runBId) {
      setLoading(false);
      setRunsError(null);
      setSummaryA(null);
      setSummaryB(null);
      setSummaryErrorA(null);
      setSummaryErrorB(null);
      setMetricsA(null);
      setMetricsB(null);
      setMetricsErrorA(null);
      setMetricsErrorB(null);
      setMarkersA([]);
      setMarkersB([]);
      setMarkersErrorA(null);
      setMarkersErrorB(null);
      setOhlcv(null);
      setOhlcvError(null);
      return;
    }
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setRunsError(null);
    setSummaryErrorA(null);
    setSummaryErrorB(null);
    setMetricsErrorA(null);
    setMetricsErrorB(null);
    setMarkersErrorA(null);
    setMarkersErrorB(null);
    setOhlcvError(null);
    setSummaryA(null);
    setSummaryB(null);
    setMetricsA(null);
    setMetricsB(null);
    setMarkersA([]);
    setMarkersB([]);
    setOhlcv(null);
    async function load() {
      const runsResult = await getRuns({ signal: controller.signal, cache: true });
      if (requestIdRef.current !== requestId || runsResult.aborted) {
        return;
      }

      let runIndex = [];
      if (runsResult.ok) {
        runIndex = Array.isArray(runsResult.data) ? runsResult.data : [];
        setRunsIndex(runIndex);
      } else {
        setRunsError(formatApiError(runsResult, "Failed to load run index"));
      }

      const runMetaA = runIndex.find((run) => run.id === runAId);
      const ohlcvParams = { limit: 2000 };
      if (runMetaA?.timeframe) {
        ohlcvParams.timeframe = runMetaA.timeframe;
      }

      const [
        summaryAResult,
        summaryBResult,
        metricsAResult,
        metricsBResult,
        markersAResult,
        markersBResult,
        ohlcvResult,
      ] = await Promise.all([
        getRunSummary(runAId, { signal: controller.signal, cache: true }),
        getRunSummary(runBId, { signal: controller.signal, cache: true }),
        getMetrics(runAId, { signal: controller.signal, cache: true }),
        getMetrics(runBId, { signal: controller.signal, cache: true }),
        getTradeMarkers(runAId, {}, { signal: controller.signal, cache: true }),
        getTradeMarkers(runBId, {}, { signal: controller.signal, cache: true }),
        getOhlcv(runAId, ohlcvParams, { signal: controller.signal, cache: true }),
      ]);

      if (
        requestIdRef.current !== requestId ||
        summaryAResult.aborted ||
        summaryBResult.aborted ||
        metricsAResult.aborted ||
        metricsBResult.aborted ||
        markersAResult.aborted ||
        markersBResult.aborted ||
        ohlcvResult.aborted
      ) {
        return;
      }

      if (summaryAResult.ok) {
        setSummaryA(summaryAResult.data);
      } else {
        setSummaryErrorA(formatApiError(summaryAResult, "Failed to load run A summary"));
      }

      if (summaryBResult.ok) {
        setSummaryB(summaryBResult.data);
      } else {
        setSummaryErrorB(formatApiError(summaryBResult, "Failed to load run B summary"));
      }

      if (metricsAResult.ok) {
        setMetricsA(metricsAResult.data);
      } else {
        setMetricsErrorA(formatApiError(metricsAResult, "Failed to load run A metrics"));
      }

      if (metricsBResult.ok) {
        setMetricsB(metricsBResult.data);
      } else {
        setMetricsErrorB(formatApiError(metricsBResult, "Failed to load run B metrics"));
      }

      if (markersAResult.ok) {
        setMarkersA(
          Array.isArray(markersAResult.data?.markers) ? markersAResult.data.markers : []
        );
      } else {
        setMarkersErrorA(formatApiError(markersAResult, "Failed to load run A markers"));
      }

      if (markersBResult.ok) {
        setMarkersB(
          Array.isArray(markersBResult.data?.markers) ? markersBResult.data.markers : []
        );
      } else {
        setMarkersErrorB(formatApiError(markersBResult, "Failed to load run B markers"));
      }

      if (ohlcvResult.ok) {
        setOhlcv(ohlcvResult.data);
      } else {
        setOhlcvError(formatApiError(ohlcvResult, "Failed to load run A OHLCV"));
      }

      setLoading(false);
    }
    load();
    return () => {
      controller.abort();
    };
  }, [router.isReady, runAId, runBId]);

  const runMetaA = useMemo(
    () => runsIndex.find((run) => run.id === runAId),
    [runsIndex, runAId]
  );
  const runMetaB = useMemo(
    () => runsIndex.find((run) => run.id === runBId),
    [runsIndex, runBId]
  );

  const symbolMismatch = useMemo(() => {
    const keyA = normalizeSymbolKey(runMetaA?.symbols);
    const keyB = normalizeSymbolKey(runMetaB?.symbols);
    if (!keyA || !keyB) {
      return false;
    }
    return keyA !== keyB;
  }, [runMetaA?.symbols, runMetaB?.symbols]);

  const timeframeMismatch = useMemo(() => {
    const tfA = runMetaA?.timeframe ? String(runMetaA.timeframe) : "";
    const tfB = runMetaB?.timeframe ? String(runMetaB.timeframe) : "";
    if (!tfA || !tfB) {
      return false;
    }
    return tfA !== tfB;
  }, [runMetaA?.timeframe, runMetaB?.timeframe]);

  const candles = useMemo(() => (ohlcv?.candles ? ohlcv.candles : []), [ohlcv]);
  const metricKeys = useMemo(() => {
    const keys = new Set();
    collectMetricKeys(metricsA).forEach((key) => keys.add(key));
    collectMetricKeys(metricsB).forEach((key) => keys.add(key));
    return Array.from(keys).sort();
  }, [metricsA, metricsB]);

  const markerSets = useMemo(() => {
    const sets = [];
    if (showRunAMarkers) {
      sets.push({
        runId: runAId,
        label: "Run A",
        markers: markersA,
        entryColor: RUN_MARKER_STYLES.runA.entry,
        exitColor: RUN_MARKER_STYLES.runA.exit,
      });
    }
    if (showRunBMarkers) {
      sets.push({
        runId: runBId,
        label: "Run B",
        markers: markersB,
        entryColor: RUN_MARKER_STYLES.runB.entry,
        exitColor: RUN_MARKER_STYLES.runB.exit,
      });
    }
    return sets;
  }, [showRunAMarkers, showRunBMarkers, markersA, markersB, runAId, runBId]);

  const invalidParams = !router.isReady
    ? null
    : !runAId || !runBId
    ? "Provide runA and runB query parameters."
    : runAId === runBId
    ? "Select two different runs to compare."
    : null;

  return (
    <main>
      <header>
        <div className="header-title">
          <h1>Compare Runs</h1>
          <span>Artifact-only compare view. Artifacts remain the source of truth.</span>
        </div>
        <Link href="/runs" className="badge info">
          Back to Runs
        </Link>
      </header>

      {invalidParams && <div className="banner">{invalidParams}</div>}
      {runsError && <div className="banner">{runsError}</div>}
      {(symbolMismatch || timeframeMismatch) && (
        <div className="banner">
          Runs differ in symbol/timeframe; marker alignment may be inaccurate.
        </div>
      )}

      {!invalidParams && (
        <section className="chart-panel" style={{ marginBottom: "24px" }}>
          <div className="chart-toolbar" style={{ justifyContent: "space-between" }}>
            <div style={{ display: "flex", gap: "12px", alignItems: "center", flexWrap: "wrap" }}>
              <label>
                Run A markers
                <input
                  type="checkbox"
                  checked={showRunAMarkers}
                  onChange={(event) => setShowRunAMarkers(event.target.checked)}
                />
              </label>
              <label>
                Run B markers
                <input
                  type="checkbox"
                  checked={showRunBMarkers}
                  onChange={(event) => setShowRunBMarkers(event.target.checked)}
                />
              </label>
            </div>
            <div className="muted" style={{ fontSize: "0.8rem" }}>
              Entry markers point up. Exit markers point down.
            </div>
          </div>
          <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", marginBottom: "8px" }}>
            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
              <span style={{ fontWeight: 600 }}>Run A</span>
              <span
                style={{
                  width: "10px",
                  height: "10px",
                  background: RUN_MARKER_STYLES.runA.entry,
                  display: "inline-block",
                  borderRadius: "2px",
                }}
              />
              <span className="muted" style={{ fontSize: "0.75rem" }}>
                entry
              </span>
              <span
                style={{
                  width: "10px",
                  height: "10px",
                  background: RUN_MARKER_STYLES.runA.exit,
                  display: "inline-block",
                  borderRadius: "2px",
                }}
              />
              <span className="muted" style={{ fontSize: "0.75rem" }}>
                exit
              </span>
              <span className="muted" style={{ fontSize: "0.75rem" }}>
                {formatValue(runAId)}
              </span>
            </div>
            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
              <span style={{ fontWeight: 600 }}>Run B</span>
              <span
                style={{
                  width: "10px",
                  height: "10px",
                  background: RUN_MARKER_STYLES.runB.entry,
                  display: "inline-block",
                  borderRadius: "2px",
                }}
              />
              <span className="muted" style={{ fontSize: "0.75rem" }}>
                entry
              </span>
              <span
                style={{
                  width: "10px",
                  height: "10px",
                  background: RUN_MARKER_STYLES.runB.exit,
                  display: "inline-block",
                  borderRadius: "2px",
                }}
              />
              <span className="muted" style={{ fontSize: "0.75rem" }}>
                exit
              </span>
              <span className="muted" style={{ fontSize: "0.75rem" }}>
                {formatValue(runBId)}
              </span>
            </div>
          </div>
          {ohlcvError && <p className="inline-warning">{ohlcvError}</p>}
          {markersErrorA && (
            <p className="inline-warning">{`Run A markers: ${markersErrorA}`}</p>
          )}
          {markersErrorB && (
            <p className="inline-warning">{`Run B markers: ${markersErrorB}`}</p>
          )}
          <CandlestickChart data={candles} markerSets={markerSets} height={360} />
          <div className="chart-status">
            <div>
              <span>Baseline OHLCV:</span>{" "}
              <strong>{formatValue(runAId || "n/a")}</strong>
            </div>
            <div>
              <span>Bars:</span> <strong>{ohlcv?.count ?? 0}</strong>
            </div>
          </div>
        </section>
      )}

      {!invalidParams && (
        <div className="card" style={{ marginBottom: "24px" }}>
          <div className="section-title">
            <h3>Metrics (artifact)</h3>
            <span className="badge info">Run A vs Run B</span>
          </div>
          {metricsErrorA && (
            <p className="inline-warning">{`Run A metrics: ${metricsErrorA}`}</p>
          )}
          {metricsErrorB && (
            <p className="inline-warning">{`Run B metrics: ${metricsErrorB}`}</p>
          )}
          {loading ? (
            <p className="muted">Loading metrics...</p>
          ) : metricKeys.length === 0 ? (
            <p className="muted">No scalar metrics available.</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th>{`Run A (${formatValue(runAId)})`}</th>
                    <th>{`Run B (${formatValue(runBId)})`}</th>
                  </tr>
                </thead>
                <tbody>
                  {metricKeys.map((key) => (
                    <tr key={key}>
                      <td>{key}</td>
                      <td>{formatValue(metricsA?.[key])}</td>
                      <td>{formatValue(metricsB?.[key])}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <div className="grid two">
        {[
          {
            label: "Run A",
            runId: runAId,
            summary: summaryA,
            summaryError: summaryErrorA,
            runMeta: runMetaA,
            link: runAId ? `/runs/${runAId}` : null,
          },
          {
            label: "Run B",
            runId: runBId,
            summary: summaryB,
            summaryError: summaryErrorB,
            runMeta: runMetaB,
            link: runBId ? `/runs/${runBId}` : null,
          },
        ].map((card) => (
          <div key={card.label} className="card">
            <div className="section-title">
              <h3>{card.label}</h3>
              <span className="badge ok">{formatValue(card.runId)}</span>
            </div>
            {loading ? (
              <p className="muted">Loading summary...</p>
            ) : card.summaryError ? (
              <p className="inline-warning">{card.summaryError}</p>
            ) : (
              <div className="kv-grid">
                {buildMetadataRows(card).map((row) => (
                  <div key={row.label}>
                    <span>{row.label}</span>
                    <strong>{row.value}</strong>
                  </div>
                ))}
              </div>
            )}
            {card.link && (
              <Link href={card.link} className="badge ok" style={{ marginTop: "12px" }}>
                Open {card.label}
              </Link>
            )}
          </div>
        ))}
      </div>
    </main>
  );
}

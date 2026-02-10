import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useMemo, useRef, useState } from "react";
import { getRunSummary, getRuns } from "../../lib/api";

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

const formatError = (result, fallback) => {
  if (!result) {
    return fallback;
  }
  if (!result.status) {
    return `${fallback}: ${result.error || "API unreachable"}`;
  }
  return `${result.error || fallback} (HTTP ${result.status})`;
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
  const [loading, setLoading] = useState(false);

  const requestIdRef = useRef(0);
  const abortRef = useRef(null);

  useEffect(() => {
    if (!router.isReady) {
      return;
    }
    if (!runAId || !runBId || runAId === runBId) {
      setLoading(false);
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
    setSummaryA(null);
    setSummaryB(null);
    async function load() {
      const [runsResult, summaryAResult, summaryBResult] = await Promise.all([
        getRuns({ signal: controller.signal, cache: true }),
        getRunSummary(runAId, { signal: controller.signal, cache: true }),
        getRunSummary(runBId, { signal: controller.signal, cache: true }),
      ]);
      if (
        requestIdRef.current !== requestId ||
        runsResult.aborted ||
        summaryAResult.aborted ||
        summaryBResult.aborted
      ) {
        return;
      }

      if (runsResult.ok) {
        setRunsIndex(Array.isArray(runsResult.data) ? runsResult.data : []);
      } else {
        setRunsError(formatError(runsResult, "Failed to load run index"));
      }

      if (summaryAResult.ok) {
        setSummaryA(summaryAResult.data);
      } else {
        setSummaryErrorA(formatError(summaryAResult, "Failed to load run A summary"));
      }

      if (summaryBResult.ok) {
        setSummaryB(summaryBResult.data);
      } else {
        setSummaryErrorB(formatError(summaryBResult, "Failed to load run B summary"));
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
          <span>Metadata-only view. Artifacts remain the source of truth.</span>
        </div>
        <Link href="/runs" className="badge info">
          Back to Runs
        </Link>
      </header>

      {invalidParams && <div className="banner">{invalidParams}</div>}
      {runsError && <div className="banner">{runsError}</div>}

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

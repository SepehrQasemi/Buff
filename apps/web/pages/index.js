import Link from "next/link";
import { useEffect, useState } from "react";
import { getDataImports, getObservabilityRuns } from "../lib/api";

export default function Home() {
  const [loading, setLoading] = useState(true);
  const [runCount, setRunCount] = useState(0);
  const [datasetCount, setDatasetCount] = useState(0);

  useEffect(() => {
    let active = true;
    const load = async () => {
      const [runsResult, importsResult] = await Promise.all([
        getObservabilityRuns(),
        getDataImports(),
      ]);
      if (!active) {
        return;
      }
      if (runsResult.ok) {
        setRunCount(Number.isFinite(runsResult.data?.total) ? runsResult.data.total : 0);
      }
      if (importsResult.ok) {
        setDatasetCount(Number.isFinite(importsResult.data?.total) ? importsResult.data.total : 0);
      }
      setLoading(false);
    };
    load();
    return () => {
      active = false;
    };
  }, []);

  return (
    <main>
      <header>
        <div className="header-title">
          <h1>Buff Local UI</h1>
          <span>Import data, create deterministic runs, inspect artifact-backed results.</span>
        </div>
        <Link className="badge info" href="/runs">
          Open Workspace
        </Link>
      </header>
      <div className="card fade-up">
        {loading ? (
          <>
            <h2>Loading local workspace</h2>
            <p style={{ color: "var(--muted)", marginTop: "8px" }}>
              Checking runs and imported datasets.
            </p>
          </>
        ) : runCount === 0 ? (
          <>
            <h2>Create Your First Run</h2>
            <p style={{ color: "var(--muted)", marginTop: "8px" }}>
              Import a CSV, choose a strategy, and run the local simulator.
            </p>
            <div style={{ marginTop: "16px", display: "flex", gap: "10px", flexWrap: "wrap" }}>
              <Link href="/runs/new">
                <button>Create Your First Run</button>
              </Link>
              {datasetCount === 0 && (
                <Link href="/runs/new">
                  <button className="secondary">Import Data</button>
                </Link>
              )}
            </div>
          </>
        ) : (
          <>
            <h2>Open Runs</h2>
            <p style={{ color: "var(--muted)", marginTop: "8px" }}>
              Inspect trades, metrics, timeline, and exports from server-generated artifacts.
            </p>
            <div style={{ marginTop: "16px" }}>
              <Link href="/runs">
                <button>Open Runs</button>
              </Link>
            </div>
          </>
        )}
      </div>
    </main>
  );
}

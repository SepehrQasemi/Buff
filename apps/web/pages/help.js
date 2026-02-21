import Link from "next/link";
import { useEffect } from "react";
import AppShell from "../components/AppShell";

const QUICK_LINKS = [
  { href: "/help#first-run", label: "First Run Checklist" },
  { href: "/help#runs-root", label: "RUNS_ROOT Issues" },
  { href: "/help#dataset-missing", label: "Dataset Missing" },
  { href: "/help#run-stuck", label: "Run Stuck" },
  { href: "/help#backend-verify", label: "Verify Backend" },
  { href: "/help#logs-report", label: "Logs and Report Bundle" },
];

export default function HelpPage() {
  useEffect(() => {
    const rawHash = decodeURIComponent(window.location.hash.replace(/^#/, ""));
    if (!rawHash) {
      return;
    }
    const anchors = [
      "first-run",
      "runs-root",
      "dataset-missing",
      "run-stuck",
      "backend-verify",
      "logs-report",
    ];
    const normalized = anchors.find(
      (anchor) =>
        rawHash === anchor ||
        rawHash.startsWith(`${anchor}/`) ||
        rawHash.startsWith(`${anchor}?`) ||
        rawHash.startsWith(`${anchor}&`)
    );
    if (!normalized || normalized === rawHash) {
      return;
    }
    const section = document.getElementById(normalized);
    if (!section) {
      return;
    }
    window.history.replaceState(null, "", `/help#${normalized}`);
    section.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  return (
    <AppShell>
      <main>
      <header>
        <div className="header-title">
          <h1>Troubleshooting Help</h1>
          <span>Quick checks for first-run setup, backend readiness, and stuck runs.</span>
        </div>
        <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
          <Link className="badge info" href="/">
            Home
          </Link>
          <Link className="badge info" href="/runs">
            Runs
          </Link>
        </div>
      </header>

      <section className="card fade-up" style={{ marginBottom: "16px" }}>
        <div className="section-title">
          <h3>Jump To</h3>
          <span className="muted">Anchored sections for direct error links</span>
        </div>
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
          {QUICK_LINKS.map((item) => (
            <Link key={item.href} href={item.href}>
              <button type="button" className="secondary">
                {item.label}
              </button>
            </Link>
          ))}
        </div>
      </section>

      <section id="first-run" className="card fade-up" style={{ marginBottom: "16px" }}>
        <div className="section-title">
          <h3>1) First Run Checklist</h3>
        </div>
        <ul style={{ margin: 0, paddingLeft: "20px", display: "grid", gap: "8px" }}>
          <li>Ensure the API process is running before opening the run wizard.</li>
          <li>Set a valid `RUNS_ROOT` directory that exists and is writable by the API process.</li>
          <li>Import a CSV that includes `timestamp`, `open`, `high`, `low`, `close`, and `volume`.</li>
          <li>Create a run and wait for lifecycle state to advance from `CREATED`.</li>
        </ul>
      </section>

      <section className="grid two" style={{ marginBottom: "16px" }}>
        <article id="runs-root" className="card fade-up">
          <div className="section-title">
            <h3>2) Common Error: RUNS_ROOT Missing or Not Writable</h3>
          </div>
          <ul style={{ margin: 0, paddingLeft: "20px", display: "grid", gap: "8px" }}>
            <li>Codes: `RUNS_ROOT_UNSET`, `RUNS_ROOT_MISSING`, `RUNS_ROOT_INVALID`, `RUNS_ROOT_NOT_WRITABLE`.</li>
            <li>Point `RUNS_ROOT` to an existing directory on the API host.</li>
            <li>Grant write permissions to the API process account.</li>
            <li>Restart API and re-check readiness at `/api/v1/health/ready`.</li>
          </ul>
        </article>

        <article id="dataset-missing" className="card fade-up">
          <div className="section-title">
            <h3>2) Common Error: Dataset Missing or Invalid</h3>
          </div>
          <ul style={{ margin: 0, paddingLeft: "20px", display: "grid", gap: "8px" }}>
            <li>Codes: `DATA_SOURCE_NOT_FOUND`, `DATA_INVALID`.</li>
            <li>Re-import CSV from the run wizard if the server cannot resolve the file path.</li>
            <li>Validate required columns and strictly increasing timestamps.</li>
            <li>Retry run creation after the import manifest appears in the UI.</li>
          </ul>
        </article>
      </section>

      <section id="run-stuck" className="card fade-up" style={{ marginBottom: "16px" }}>
        <div className="section-title">
          <h3>2) Common Error: Run Stuck or Not Found</h3>
        </div>
        <ul style={{ margin: 0, paddingLeft: "20px", display: "grid", gap: "8px" }}>
          <li>If a new run remains in `CREATED`, use retry and keep the page open until lifecycle advances.</li>
          <li>If you get `RUN_NOT_FOUND`, confirm the run id exists under the current `RUNS_ROOT`.</li>
          <li>If artifacts are missing/corrupted, recreate the run to regenerate output files.</li>
        </ul>
      </section>

      <section id="backend-verify" className="card fade-up" style={{ marginBottom: "16px" }}>
        <div className="section-title">
          <h3>3) How to Verify Backend (health/ready)</h3>
        </div>
        <div className="grid two">
          <div className="kpi">
            <span>Health Endpoint</span>
            <strong>/api/v1/health</strong>
          </div>
          <div className="kpi">
            <span>Readiness Endpoint</span>
            <strong>/api/v1/health/ready</strong>
          </div>
        </div>
        <p className="muted" style={{ marginTop: "12px", marginBottom: 0 }}>
          `health` confirms the API process is alive. `health/ready` confirms the runtime is ready to serve runs.
        </p>
      </section>

        <section id="logs-report" className="card fade-up">
        <div className="section-title">
          <h3>4) Where to Find Logs / Report Bundle</h3>
        </div>
        <ul style={{ margin: 0, paddingLeft: "20px", display: "grid", gap: "8px" }}>
          <li>API terminal output is the primary source for request-time errors.</li>
          <li>Run-level artifacts live under your configured `RUNS_ROOT` path.</li>
          <li>Release gate reports are written to `reports/release_gate_report.json` in repo root.</li>
          <li>Capture these details when reporting issues so failures are reproducible.</li>
        </ul>
        </section>
      </main>
    </AppShell>
  );
}

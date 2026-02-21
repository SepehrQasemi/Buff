import Link from "next/link";
import AppShell from "../../components/AppShell";

export default function ExperimentsPage() {
  return (
    <AppShell>
      <main>
        <header>
          <div className="header-title">
            <h1>Experiments</h1>
            <span>Experiment orchestration and comparison artifacts.</span>
          </div>
          <Link className="badge info" href="/runs">
            Back to Runs
          </Link>
        </header>

        <section className="card fade-up">
          <h2 style={{ marginTop: 0 }}>Experiments (S7) coming soon</h2>
          <p className="muted" style={{ marginBottom: 0 }}>
            Use Runs for now while the dedicated experiments flow is finalized.
          </p>
          <div style={{ marginTop: "16px" }}>
            <Link href="/runs">
              <button type="button">Open Runs</button>
            </Link>
          </div>
        </section>
      </main>
    </AppShell>
  );
}

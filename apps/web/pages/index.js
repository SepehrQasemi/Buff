import Link from "next/link";

export default function Home() {
  return (
    <main>
      <header>
        <div className="header-title">
          <h1>Buff Local UI</h1>
          <span>Read-only dashboard for run artifacts.</span>
        </div>
        <Link className="badge info" href="/runs">
          Browse Runs
        </Link>
      </header>
      <div className="card fade-up">
        <h2>Start in Runs</h2>
        <p style={{ color: "var(--muted)", marginTop: "8px" }}>
          Inspect decisions, trades, and fail-closed errors without touching execution.
        </p>
        <div style={{ marginTop: "16px" }}>
          <Link href="/runs">
            <button>Open Runs</button>
          </Link>
        </div>
      </div>
    </main>
  );
}

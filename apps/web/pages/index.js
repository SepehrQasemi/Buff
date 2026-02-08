import Link from "next/link";

export default function Home() {
  return (
    <main>
      <header>
        <div className="header-title">
          <h1>Buff Local UI</h1>
          <span>Chart-first, read-only workspace for artifact truth.</span>
        </div>
        <Link className="badge info" href="/runs">
          Open Workspace
        </Link>
      </header>
      <div className="card fade-up">
        <h2>Start in Runs</h2>
        <p style={{ color: "var(--muted)", marginTop: "8px" }}>
          Inspect trades, metrics, and timeline events directly from artifacts.
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

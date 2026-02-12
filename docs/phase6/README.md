# Phase-6: Make Buff Actually Usable

## Purpose
Phase-6 moves Buff from fixture-driven demos to real, user-created runs with durable storage, real data ingest, and a safe run-creation UX. It keeps the system read-only for execution and does not introduce live trading.

## No-skip Rule
Stage N must meet its Definition of Done and pass its mandatory gates before Stage N+1 begins. No parallel execution across stages and no partial carryover of unfinished requirements.

## Scope Boundary
In-scope:
- Create runs from real inputs (CSV first), generate artifacts, and render them in the UI.
- Durable run storage under RUNS_ROOT with a crash-safe registry.
- Minimal API and UI flow to create and list runs.

Non-goals:
- Live trading or broker execution controls.
- Strategy invention or runtime strategy editing in the UI.
- Multi-tenant SaaS, hosted accounts, or remote execution.

## Stages

| Stage | Goal | DoD Summary | Spec |
| --- | --- | --- | --- |
| Stage 1: Real Run Builder | Create a deterministic run from CSV and register it | run_id deterministic, required artifacts written, /runs/{id} renders | [SPEC.md#stage-1-real-run-builder](SPEC.md#stage-1-real-run-builder) |
| Stage 2: Durable Storage | Make RUNS_ROOT and registry crash-safe | atomic index, restart persistence, no partial runs | [SPEC.md#stage-2-durable-storage](SPEC.md#stage-2-durable-storage) |
| Stage 3: Real Data Ingestion | Harden ingest and reproducible resampling | validation fails closed, quality report, deterministic outputs | [SPEC.md#stage-3-real-data-ingestion](SPEC.md#stage-3-real-data-ingestion) |
| Stage 4: Usable UX | Add /runs/new create flow | UI creates run, progress + errors, redirect to /runs/{id} | [SPEC.md#stage-4-usable-ux](SPEC.md#stage-4-usable-ux) |
| Stage 5: Reliability and Safety | Add limits, health, and kill switch | enforced limits, health readiness, structured logs | [SPEC.md#stage-5-reliability-and-safety](SPEC.md#stage-5-reliability-and-safety) |

## Single Source of Truth Gates
Run Python commands via `\.venv\Scripts\python.exe` to ensure the venv interpreter is used.

```powershell
.\.venv\Scripts\python.exe scripts\verify_phase1.py --with-services
.\.venv\Scripts\python.exe -m tools.release_gate --strict --timeout-seconds 900
.\.venv\Scripts\python.exe scripts\phase6_release_gate.py
node apps/web/scripts/smoke.mjs
node apps/web/scripts/ui-smoke.mjs
```

## References
- [SPEC.md](SPEC.md): Execution spec, stages, UX, and milestone demos.
- [CONTRACTS.md](CONTRACTS.md): Run builder, data, storage, and API contracts.

Current status: Phase-6 not started (Stage 1 next).

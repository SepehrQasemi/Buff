# Product Overview And Journeys

## Table Of Contents
- [What Buff Is](#what-buff-is)
- [What Buff Is Not](#what-buff-is-not)
- [User Journeys](#user-journeys)
- [Key Invariants](#key-invariants)
- [Canonical Links](#canonical-links)

## What Buff Is
Buff is a deterministic, artifact-first strategy analysis lab with a chart-first UI.
It is designed for reproducibility, explainability, and fail-closed behavior.

## What Buff Is Not
Non-goals for current scope:
- Live broker trading terminal
- UI-triggered trade execution
- Hidden recomputation of metrics or strategy outputs
- Multi-tenant hosted product

## User Journeys
Primary journeys:
1. First run from CSV input and local services.
2. Open a run workspace and inspect chart, trades, metrics, and timeline.
3. Export a run report for sharing and review.

Detailed references:
- First run: [FIRST_RUN.md](./FIRST_RUN.md)
- Run workspace behavior: [UI_SPEC.md](./UI_SPEC.md)
- Export report workflow: [FIRST_RUN.md#export-report-1-minute](./FIRST_RUN.md#export-report-1-minute)

## Key Invariants
- Determinism: same canonical inputs produce the same run identity and artifacts.
- Fail-closed: missing or invalid dependencies return explicit errors.
- Read-only UI: no buy/sell/broker execution controls.
- Artifact truth: UI reads produced artifacts, not hidden recomputation.

## Canonical Links
- Architecture boundaries: [02_ARCHITECTURE_BOUNDARIES.md](./02_ARCHITECTURE_BOUNDARIES.md)
- Contracts and schemas: [03_CONTRACTS_AND_SCHEMAS.md](./03_CONTRACTS_AND_SCHEMAS.md)
- Roadmap and status: [04_ROADMAP_AND_DELIVERY_CHECKLIST.md](./04_ROADMAP_AND_DELIVERY_CHECKLIST.md)
- Dev runbook: [05_RUNBOOK_DEV_WORKFLOW.md](./05_RUNBOOK_DEV_WORKFLOW.md)

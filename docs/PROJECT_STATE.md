CURRENT_STAGE=S2_MULTI_USER_ISOLATION_LAYER
OPEN_PRS_TO_DECIDE=0
LAST_STAGE_RELEVANT_PR=215
LAST_STAGE_RELEVANT_SHA=bd8db815c0e63546db5a3f339bbe2d226a229aff
S2_IMPLEMENTED_MAIN_SHA=7056fb402ad1c13e61c7c2d1294271fc50b128ca
SNAPSHOT_SEMANTICS=Stage snapshot fields track stage/governance-relevant merges, not every merge on main.

NEXT_3_ACTIONS=
- Keep docs PRs in Lane 1 (docs/** and README.md only).
- Keep tooling changes in Lane 2 (scripts/**) and never mix them into docs-only PRs.
- Keep operational command strings sourced from docs/05_RUNBOOK_DEV_WORKFLOW.md.

HOW_TO_REFRESH=
- Use canonical operational commands from docs/05_RUNBOOK_DEV_WORKFLOW.md.
- Query live PR state from GitHub before refreshing this snapshot.
- Update: LAST_STAGE_RELEVANT_PR / LAST_STAGE_RELEVANT_SHA / OPEN_PRS_TO_DECIDE / NEXT_3_ACTIONS

# PROJECT_STATE

## Authoritative Notice

This file is the single source of truth for:
- Current project stage
- Current objective
- Definition of Done
- Active constraints
- Next transition gate

No other document determines current stage.

---

## Machine-Readable Snapshot


CURRENT_STAGE=S2_MULTI_USER_ISOLATION_LAYER
OPEN_PRS_TO_DECIDE=0
LAST_STAGE_RELEVANT_PR=215
LAST_STAGE_RELEVANT_SHA=bd8db815c0e63546db5a3f339bbe2d226a229aff
S2_IMPLEMENTED_MAIN_SHA=7056fb402ad1c13e61c7c2d1294271fc50b128ca
OPS_COMMAND_SOURCE=docs/05_RUNBOOK_DEV_WORKFLOW.md

---

## Current Stage
S2 - Multi-User Isolation Layer

## Stage Description
Fail-closed, artifact-driven, deterministic analysis system.
No trade execution.
No broker integration.
No live state mutation.

## Current Objective
Preserve S2 isolation guarantees and prepare S3 controlled execution simulation planning without weakening deterministic/runtime safeguards.

## Definition of Done
- All normative constraints centralized
- No broken links
- Single-source operational command strings: runnable command blocks and inline runnable commands appear only in `docs/05_RUNBOOK_DEV_WORKFLOW.md`.
  Other docs may mention gate names but must link to the runbook.
- CI green on current `main` tip SHA for active workflows (historical runs from decommissioned workflows may remain in history)
- release_gate PASS

## Active Constraints
- Execution is out of scope
- Broker APIs forbidden
- Deterministic runtime only
- Fail-closed error handling
- Canonical contract authority enforced

## Next Stage Candidate
S3_CONTROLLED_EXECUTION_SIMULATION

## S2 Acceptance Evidence
- Runtime acceptance validated on `main` via `/api/v1/ready`, `/api/v1/runs`, `/api/v1/runs/{id}/metrics`, and `/api/v1/runs/{id}/diagnostics`.
- Header-only mode evidence: alice sees run, bob sees none, and bob cross-user metrics/diagnostics return `404 RUN_NOT_FOUND`.
- HMAC mode evidence: valid signed alice request succeeds, tampered user header is blocked, and replay timestamp outside skew is blocked.
- Observed fail-closed error codes: `USER_MISSING`, `AUTH_INVALID`, `TIMESTAMP_INVALID`, `AUTH_MISSING`, `RUN_NOT_FOUND`.

## Transition Gate Requirements (S0 -> S1, Historical And Satisfied)
- Run indexing layer
- Queryable artifact registry
- Structured runtime metrics
- Observability documentation: `docs/OBSERVABILITY.md`
- Updated PROJECT_STATE.md

## Workflow Lanes
- Lane 1 (DocsOnly): `docs/**` and `README.md` only.
- Lane 2 (Tooling): `scripts/**` and automation support files.

## Solo Mode
- Local guardrails are warn-only to avoid blocking solo development loops.
- PR gate enforcement is strict and authoritative.
- Untracked `scripts/**` files are allowed while developing locally.
- Before merging a DocsOnly PR, any `scripts/**` local work must be:
  - committed in a Tooling lane branch/PR, or
  - removed from local workspace.

## Last Verified Commit

bd8db815c0e63546db5a3f339bbe2d226a229aff


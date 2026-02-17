CURRENT_STAGE=S1_OBSERVABILITY_AND_RUN_INTELLIGENCE_LAYER
OPEN_PRS_TO_DECIDE=0
LAST_STAGE_RELEVANT_PR=209
LAST_STAGE_RELEVANT_SHA=254707b1700def672c0d465223cb2b0a383328db
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


CURRENT_STAGE=S1_OBSERVABILITY_AND_RUN_INTELLIGENCE_LAYER
OPEN_PRS_TO_DECIDE=0
LAST_STAGE_RELEVANT_PR=209
LAST_STAGE_RELEVANT_SHA=254707b1700def672c0d465223cb2b0a383328db
OPS_COMMAND_SOURCE=docs/05_RUNBOOK_DEV_WORKFLOW.md

---

## Current Stage
S0 - Deterministic Analysis-Only Engine

## Stage Description
Fail-closed, artifact-driven, deterministic analysis system.
No trade execution.
No broker integration.
No live state mutation.

## Current Objective
Harden documentation boundaries and enforce contract authority.

## Definition of Done
- All normative constraints centralized
- No broken links
- Single-source operational command strings: runnable command blocks and inline runnable commands appear only in `docs/05_RUNBOOK_DEV_WORKFLOW.md`.
  Other docs may mention gate names but must link to the runbook.
- CI green (latest runs for active workflows on `main` pass; historical runs from decommissioned workflows may remain in history)
- release_gate PASS

## Active Constraints
- Execution is out of scope
- Broker APIs forbidden
- Deterministic runtime only
- Fail-closed error handling
- Canonical contract authority enforced

## Next Stage Candidate
S1 - Observability And Run Intelligence Layer

## Transition Gate Requirements (S0 -> S1)
- Run indexing layer
- Queryable artifact registry
- Structured runtime metrics
- Observability documentation
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

6337a0be9274bbd39ec6433133878914b7deed9c

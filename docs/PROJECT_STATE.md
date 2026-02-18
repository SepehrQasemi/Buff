CURRENT_STAGE=S4_RISK_ENGINE_MATURITY
OPEN_PRS_TO_DECIDE=0
LAST_STAGE_RELEVANT_PR=225
LAST_STAGE_RELEVANT_SHA=3e36db11a5706006bb464f046d2b1ef531f4182f
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


CURRENT_STAGE=S4_RISK_ENGINE_MATURITY
OPEN_PRS_TO_DECIDE=0
LAST_STAGE_RELEVANT_PR=225
LAST_STAGE_RELEVANT_SHA=3e36db11a5706006bb464f046d2b1ef531f4182f
S2_IMPLEMENTED_MAIN_SHA=7056fb402ad1c13e61c7c2d1294271fc50b128ca
OPS_COMMAND_SOURCE=docs/05_RUNBOOK_DEV_WORKFLOW.md

---

## Current Stage
S4 - Risk Engine Maturity

## Stage Description
Fail-closed, artifact-driven, deterministic analysis system.
No trade execution.
No broker integration.
No live state mutation.

## Current Objective
Build S4 risk semantics and controls on top of completed S3 controlled execution simulation without weakening deterministic/runtime safeguards.

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
S5_EXECUTION_SAFETY_BOUNDARIES

## S3 Acceptance Evidence
- S3 runtime acceptance validated on `main` at `3e36db11a5706006bb464f046d2b1ef531f4182f` with deterministic run/replay behavior.
- Strict release gate includes and passes: `s3_double_run_compare`, `s3_input_digest_verification`, `s3_cross_tenant_isolation`, `s3_no_network`, `s3_no_live_execution_path`, `s3_artifact_pack_completeness`, and `s3_smoke_demo`.
- Stage-relevant completion recorded by PR #225 and SHA `3e36db11a5706006bb464f046d2b1ef531f4182f`.

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

3e36db11a5706006bb464f046d2b1ef531f4182f

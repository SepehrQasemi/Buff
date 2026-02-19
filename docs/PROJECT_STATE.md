CURRENT_STAGE=S5_EXECUTION_SAFETY_BOUNDARIES
OPEN_PRS_TO_DECIDE=0
LAST_STAGE_RELEVANT_PR=240
LAST_STAGE_RELEVANT_SHA=558e427c0b0902d8c6dbd9aed532186a3d5f6a4d
S2_IMPLEMENTED_MAIN_SHA=7056fb402ad1c13e61c7c2d1294271fc50b128ca
SNAPSHOT_SEMANTICS=Stage snapshot fields track stage/governance-relevant merges, not every merge on main.

NEXT_3_ACTIONS=
- Monitor SIM_ONLY enforcement in CI.
- Evaluate need for execution capability surface tightening.
- Continue Phase-6 product iteration (UX + research tools).

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


CURRENT_STAGE=S5_EXECUTION_SAFETY_BOUNDARIES
OPEN_PRS_TO_DECIDE=0
LAST_STAGE_RELEVANT_PR=240
LAST_STAGE_RELEVANT_SHA=558e427c0b0902d8c6dbd9aed532186a3d5f6a4d
S2_IMPLEMENTED_MAIN_SHA=7056fb402ad1c13e61c7c2d1294271fc50b128ca
OPS_COMMAND_SOURCE=docs/05_RUNBOOK_DEV_WORKFLOW.md

---

## Current Stage
S5_EXECUTION_SAFETY_BOUNDARIES

## Stage Description
Fail-closed, artifact-driven, deterministic analysis system with execution safety boundaries.
SIM_ONLY execution is enforced in runtime manifests and capabilities.
Execution overrides (`execution_mode`, `live`, `broker`) are rejected fail-closed.
Runtime guardrails preserve network ingest isolation and deterministic behavior.
No broker integration.
No live state mutation.

## Current Objective
Harden execution safety boundaries by enforcing SIM_ONLY behavior, rejecting execution overrides, preserving runtime/network guardrails, and keeping strict verification gates green.

## Definition of Done
- All normative constraints centralized
- No broken links
- Single-source operational command strings: runnable command blocks and inline runnable commands appear only in `docs/05_RUNBOOK_DEV_WORKFLOW.md`.
  Other docs may mention gate names but must link to the runbook.
- SIM_ONLY execution mode is written to run manifests and capabilities.
- Execution override fields (`execution_mode`, `live`, `broker`) are rejected fail-closed with stable API errors.
- Runtime guardrails keep network ingest isolation and deterministic behavior intact.
- `release_gate --strict --timeout-seconds 900` PASS on `main`.
- CI green on current `main` tip SHA for active workflows (historical runs from decommissioned workflows may remain in history)
- release_gate PASS

## Active Constraints
- Execution is out of scope
- Broker APIs forbidden
- Deterministic runtime only
- Fail-closed error handling
- Canonical contract authority enforced

## Next Stage Candidate
S6_PLATFORM_OBSERVABILITY_LAYER

## S3 Acceptance Evidence
- S3 runtime acceptance validated on `main` at `3e36db11a5706006bb464f046d2b1ef531f4182f` with deterministic run/replay behavior.
- Strict release gate includes and passes: `s3_double_run_compare`, `s3_input_digest_verification`, `s3_cross_tenant_isolation`, `s3_no_network`, `s3_no_live_execution_path`, `s3_artifact_pack_completeness`, and `s3_smoke_demo`.
- Stage-relevant completion recorded by PR #225 and SHA `3e36db11a5706006bb464f046d2b1ef531f4182f`.

## S5 Acceptance Evidence
- Lean S5 guardrails are merged on `main` in PR #240 (`phase6: enforce SIM_ONLY run manifest + reject execution overrides`).
- Stage-relevant authority is anchored at PR #240 with SHA `558e427c0b0902d8c6dbd9aed532186a3d5f6a4d`.
- Runtime acceptance confirms SIM_ONLY manifest/capability enforcement and fail-closed rejection of execution overrides, with strict release-gate enforcement.

## Transition Gate Requirements (S0 -> S1, Historical And Satisfied)
- Run indexing layer
- Queryable artifact registry
- Structured runtime metrics
- Observability documentation: `docs/OBSERVABILITY.md`
- Updated PROJECT_STATE.md

## Workflow Lanes
- Lane 1 (DocsOnly): `docs/**` and `README.md` only.
- Lane 2 (Tooling): `tools/**` and `scripts/**` only.
- Lane 3 (Runtime): `src/**`, `apps/**`, and `tests/**` only.

## Solo Mode
- Local guardrails are warn-only to avoid blocking solo development loops.
- PR gate enforcement is strict and authoritative.
- Untracked `tools/**` or `scripts/**` files are allowed while developing locally.
- Before merging a DocsOnly PR, any `tools/**` or `scripts/**` local work must be:
  - committed in a Tooling lane branch/PR, or
  - removed from local workspace.

## Last Verified Commit

558e427c0b0902d8c6dbd9aed532186a3d5f6a4d

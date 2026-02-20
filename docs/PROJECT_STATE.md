CURRENT_STAGE=S6_PLATFORM_OBSERVABILITY_LAYER
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


CURRENT_STAGE=S6_PLATFORM_OBSERVABILITY_LAYER
OPEN_PRS_TO_DECIDE=0
LAST_STAGE_RELEVANT_PR=240
LAST_STAGE_RELEVANT_SHA=558e427c0b0902d8c6dbd9aed532186a3d5f6a4d
S2_IMPLEMENTED_MAIN_SHA=7056fb402ad1c13e61c7c2d1294271fc50b128ca
OPS_COMMAND_SOURCE=docs/05_RUNBOOK_DEV_WORKFLOW.md

---

## Current Stage
S6_PLATFORM_OBSERVABILITY_LAYER

## Stage Description
Read-only platform observability and health surface over deterministic run artifacts.
Health and observability endpoints provide diagnostics without mutating runtime state.
Legacy migration is explicit via a non-observability admin endpoint.
No broker integration.
No live execution path.

## Current Objective
Enforce read-only observability behavior by keeping health endpoints read-only, keeping observability routes read-only, routing legacy migration through explicit admin POST, and maintaining no-write enforcement tests.

## Definition of Done
- All observability routes are GET-only and read-only.
- No filesystem mutation occurs on observability/health GET request paths.
- Dedicated no-write tests cover `GET /api/v1/health/ready`, `GET /api/v1/observability/*`, and `GET /api/v1/runs/{run_id}/metrics`.
- `python -m tools.release_gate --strict --timeout-seconds 900` PASS on `main`.
- CI green on current `main` tip SHA for active workflows.

## Active Constraints
- Execution is out of scope
- Broker APIs forbidden
- Deterministic runtime only
- Fail-closed error handling
- Canonical contract authority enforced

## Next Stage Candidate
S7_PERSONAL_RESEARCH_ENGINE

## S7 Preview (Candidate)
- Objective:
  Extend Buff from a single-run artifact viewer into a personal quant research lab built on deterministic experiment workflows and artifact-backed analysis.
- Non-goals:
  No live trading path, no broker integration, no multi-user SaaS scope, and no cloud deployment requirements.
- Value Target Persona:
  Solo quant researcher who needs repeatable experiment execution, ranked comparisons, and artifact-grounded insight workflows on local infrastructure.

## Evidence Note (S6 Stage Flip)
- Runtime hardening PR: #264 https://github.com/Buff-Trading-AI/Buff/pull/264
- No-write enforcement tests: `tools/test_s6_observability_surface.py`
- Main SHA validated for strict gate: `cadccad38c3748212dd94dd80378a51d53be61e9` (`python -m tools.release_gate --strict --timeout-seconds 900` PASS)

## S3 Acceptance Evidence
- S3 runtime acceptance validated on `main` at `3e36db11a5706006bb464f046d2b1ef531f4182f` with deterministic run/replay behavior.
- Strict release gate includes and passes: `s3_double_run_compare`, `s3_input_digest_verification`, `s3_cross_tenant_isolation`, `s3_no_network`, `s3_no_live_execution_path`, `s3_artifact_pack_completeness`, and `s3_smoke_demo`.
- Stage-relevant completion recorded by PR #225 and SHA `3e36db11a5706006bb464f046d2b1ef531f4182f`.

## S5 Acceptance Evidence
- Lean S5 guardrails are merged on `main` in PR #240 (`phase6: enforce SIM_ONLY run manifest + reject execution overrides`).
- Stage-relevant authority is anchored at PR #240 with SHA `558e427c0b0902d8c6dbd9aed532186a3d5f6a4d`.
- Runtime acceptance confirms SIM_ONLY manifest/capability enforcement and fail-closed rejection of execution overrides, with strict release-gate enforcement.

## S6 Platform Observability & Productization - Acceptance Evidence
STAGE_TOKEN=S6_PLATFORM_OBSERVABILITY_LAYER
DATE_VERIFIED_UTC=2026-02-19
MAIN_SHA=cb91cc6ddaeb38565db0294c446eca80f8ec2fa8
PRS=#244 https://github.com/Buff-Trading-AI/Buff/pull/244; #245 https://github.com/Buff-Trading-AI/Buff/pull/245; #246 https://github.com/Buff-Trading-AI/Buff/pull/246; #247 https://github.com/Buff-Trading-AI/Buff/pull/247
CI_WORKFLOWS=https://github.com/Buff-Trading-AI/Buff/actions/runs/22183407044; https://github.com/Buff-Trading-AI/Buff/actions/runs/22183926606; https://github.com/Buff-Trading-AI/Buff/actions/runs/22184643631; https://github.com/Buff-Trading-AI/Buff/actions/runs/22184943839
- Runtime evidence: `GET /api/v1/health/ready` is present for readiness checks.
- Runtime evidence: observability surfaces are present at `GET /api/v1/observability/runs`, `GET /api/v1/observability/runs/{run_id}`, and `GET /api/v1/observability/registry`.
- Runtime evidence: deterministic report export is present at `GET /api/v1/runs/{run_id}/report/export`.
- Runtime evidence: SIM_ONLY invariant preserved; observability surfaces are GET-only; no network execution surface added.
- Risk note: plugin validation runtime timeout was deliberately increased from 2s to 4s to reduce flakes under load, while keeping fail-closed behavior.

## PRODUCTIZATION STATUS SNAPSHOT (Post S5)
- Docker named volume default for RUNS_ROOT: not merged on `main` in this snapshot; compose default remains `${RUNS_ROOT_HOST:-./.runs_compose}:/runs`.
- UI Create Run Wizard is implemented (`/runs/new`: import data -> choose strategy -> configure -> create run).
- Observability endpoints are present (`/api/v1/observability/registry`, `/api/v1/observability/runs`, `/api/v1/observability/runs/{run_id}`).
- Report export is functional (`/api/v1/runs/{run_id}/report/export`).
- UI Journey Runner is implemented (Playwright-based, `apps/web/scripts/user-journey.spec.mjs`).
- Known issue: historical Windows bind mount flakiness can surface intermittent `RUNS_ROOT_NOT_WRITABLE` 503 responses.
- Known issue: NumPy/pyarrow ABI warning appears in API container logs; currently non-blocking but tracked.

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

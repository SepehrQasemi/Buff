CURRENT_STAGE=S7_PERSONAL_RESEARCH_ENGINE
OPEN_PRS_TO_DECIDE=0
LAST_STAGE_RELEVANT_PR=275
LAST_STAGE_RELEVANT_SHA=b3aa5df597cf31e008aab90854cce2ad251e0c5b
S2_IMPLEMENTED_MAIN_SHA=7056fb402ad1c13e61c7c2d1294271fc50b128ca
SNAPSHOT_SEMANTICS=Stage snapshot fields track stage/governance-relevant merges, not every merge on main.

NEXT_3_ACTIONS=
- Keep S7 experiment and strict gate checks green in CI.
- Expand deterministic experiment analysis UX on artifact-backed comparison surfaces.
- Prepare post-S7 scope decision for the External Integration Layer.

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


CURRENT_STAGE=S7_PERSONAL_RESEARCH_ENGINE
OPEN_PRS_TO_DECIDE=0
LAST_STAGE_RELEVANT_PR=275
LAST_STAGE_RELEVANT_SHA=b3aa5df597cf31e008aab90854cce2ad251e0c5b
S2_IMPLEMENTED_MAIN_SHA=7056fb402ad1c13e61c7c2d1294271fc50b128ca
OPS_COMMAND_SOURCE=docs/05_RUNBOOK_DEV_WORKFLOW.md

---

## Current Stage
S7_PERSONAL_RESEARCH_ENGINE

## Stage Description
Deterministic personal research engine over run artifacts.
S7 adds experiment orchestration and multi-run comparison while preserving SIM_ONLY safety boundaries.
No broker integration.
No live execution path.

## Current Objective
Run deterministic experiment workflows and artifact-backed multi-run analysis for single-user research without expanding execution authority.

## Definition of Done
- User can define a deterministic experiment input over canonical candidate run configs.
- System writes truthful experiment artifacts (`experiment_manifest.json`, `comparison_summary.json`) derived from run artifacts.
- Partial candidate failures are represented explicitly (fail-closed) with canonical error envelopes.
- Candidate caps and per-experiment lock timeout behavior are enforced and covered by strict gate checks.
- `python -m tools.release_gate --strict --timeout-seconds 900` PASS on `main`.
- CI green on current `main` tip SHA for active workflows.

## Active Constraints
- Execution is out of scope
- Broker APIs forbidden
- Deterministic runtime only
- Fail-closed error handling
- Canonical contract authority enforced

## Next Stage Candidate
TBD
Next stage token not yet defined; see `docs/06_SYSTEM_EVOLUTION_ROADMAP.md` Future Layer section.

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

## S7 Acceptance Evidence
- S7 runtime experiment surface is merged on `main` in PR #270 at SHA `a44ab2418c8b49873b95ec182beed3596132f2f0`.
- S7 strict release gate checks are merged on `main` in PR #271 at SHA `27180ca94a54c40d5efa5057a33e912e6c5d8787` (merged at `2026-02-21T11:52:56Z`).
- Runtime caps and lock-timeout hardening are merged on `main` in PR #273 at SHA `48ed3d019f3926088b189a3a36a288bdb179c98f`; strict gate enforcement for those guarantees is merged in PR #275 at SHA `b3aa5df597cf31e008aab90854cce2ad251e0c5b`.
- Error-code registry alignment for experiment caps/lock-timeout is merged on `main` in PR #274 at SHA `76853cee4fbd03677b4523864b73ac5fe9651c64`.
- Strict release gate on `main` includes `s7_experiment_artifact_contract`, `s7_experiment_determinism`, `s7_experiment_fail_closed_partial`, `s7_experiment_caps_enforced`, and `s7_experiment_lock_enforced`, and is PASS on `main` SHA `b3aa5df597cf31e008aab90854cce2ad251e0c5b`.

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

b3aa5df597cf31e008aab90854cce2ad251e0c5b

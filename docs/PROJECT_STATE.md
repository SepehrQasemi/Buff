CURRENT_STAGE=S2_PAPER_LIVE_FUTURES
NEXT_STAGE_CANDIDATE=S3_RESEARCH_ENGINE_HARDENING
OPEN_PRS_TO_DECIDE=0
LAST_RESET_DATE_UTC=2026-02-24
LAST_VERIFIED_COMMIT=d7b222e30ff19fe8112a35461c1c04740263d391
STAGE_LADDER=S0_REFOUNDATION|S1_ONLINE_DATA_PLANE|S2_PAPER_LIVE_FUTURES|S3_RESEARCH_ENGINE_HARDENING|S4_RISK_ENGINE_MATURITY|S5_EXECUTION_CONNECTOR_FUTURE
OPS_COMMAND_SOURCE=docs/05_RUNBOOK_DEV_WORKFLOW.md
SNAPSHOT_SEMANTICS=Machine-readable stage snapshot fields track current authoritative direction and transition readiness.
End-to-end development order and forbidden moves are defined in [docs/MASTER_DEVELOPMENT_PATH.md](./MASTER_DEVELOPMENT_PATH.md).

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

CURRENT_STAGE=S2_PAPER_LIVE_FUTURES
NEXT_STAGE_CANDIDATE=S3_RESEARCH_ENGINE_HARDENING
OPEN_PRS_TO_DECIDE=0
LAST_RESET_DATE_UTC=2026-02-24
LAST_VERIFIED_COMMIT=d7b222e30ff19fe8112a35461c1c04740263d391
STAGE_LADDER=S0_REFOUNDATION|S1_ONLINE_DATA_PLANE|S2_PAPER_LIVE_FUTURES|S3_RESEARCH_ENGINE_HARDENING|S4_RISK_ENGINE_MATURITY|S5_EXECUTION_CONNECTOR_FUTURE
OPS_COMMAND_SOURCE=docs/05_RUNBOOK_DEV_WORKFLOW.md

---

## Current Stage
S2_PAPER_LIVE_FUTURES

## Current Objective
Run deterministic paper-live futures simulation from canonical data with bar-close-only decisions, deterministic execution modeling, and replay-verifiable artifacts.

## Active Constraints
- Runtime safety is fail-closed by default.
- Deterministic artifact contracts are mandatory.
- Simulation must be driven only from canonical data artifacts.
- Strategy and risk evaluation are bar-close only.
- Online data collection may feed inputs, but no direct exchange calls are allowed in simulation.
- No production broker connector implementation in the current stage.

## S1 Exit Evidence
- S1 completion PRs merged:
  - https://github.com/Buff-Trading-AI/Buff/pull/300
  - https://github.com/Buff-Trading-AI/Buff/pull/303
- CI + release gate proof on S1 closeout commit `3fcb50d23051ed2dde96d3be8a0583efeeae7a83`:
  - https://github.com/Buff-Trading-AI/Buff/actions/runs/22393042614/job/64819662319

## Stage Ladder

### S0_REFOUNDATION
Objective:
- Establish canonical product direction, contracts, and stage system for futures R&D and paper-live progression.

Definition of Done (explicit, testable):
- `docs/PROJECT_STATE.md`, `docs/PRODUCT_SPEC.md`, `docs/06_DATA_PLANE_ONLINE.md`, `docs/07_PAPER_LIVE_FUTURES.md`, `docs/08_RESEARCH_LOOP.md`, and `docs/09_EXECUTION_FUTURE.md` exist and are internally consistent.
- Legacy stage/phase docs are archived under `docs/_archive/20260224_legacy_reset/` with explicit non-authoritative header.
- No active doc claims stage authority except this file.

Active Constraints:
- Documentation reset only; no runtime behavior change implied by this stage alone.
- Historical content remains available in archive and is not authoritative.

Transition Gate:
- Documentation consistency checks pass: no broken local links in active docs, no legacy stage tokens in active docs, no runnable command blocks outside the runbook.

### S1_ONLINE_DATA_PLANE
Objective:
- Implement mandatory online futures market data ingestion with deterministic canonicalization and replayable artifacts.

Definition of Done (explicit, testable):
- Feed adapter supports websocket-first ingestion with REST backfill fallback.
- Raw immutable event log artifact is produced for every ingest session.
- Canonical OHLCV output is reproducible from raw events with identical hashes across replays.
- Gap, late-data, and revision policies are enforced and artifact-recorded.

Active Constraints:
- Data plane has no execution authority.
- Fail-closed behavior on feed inconsistency, digest mismatch, or schema violation.

Transition Gate:
- Deterministic replay tests pass for `raw -> canonical` reconstruction and artifact digest stability.

### S2_PAPER_LIVE_FUTURES
Objective:
- Deliver realistic paper-live futures simulation as the primary execution mode for validation.

Definition of Done (explicit, testable):
- Bar-close decision loop executes against canonical market data.
- Baseline fee, slippage, funding, position, and conservative liquidation models are enforced.
- Risk kill-switch and hard safety caps are enforced at runtime.
- Required paper-live artifacts are produced and replay-verifiable.

Active Constraints:
- No external order placement.
- Simulation must remain deterministic under fixed input artifacts.

Transition Gate:
- Paper-live replay parity passes with stable metrics/trade artifacts under identical inputs.

### S3_RESEARCH_ENGINE_HARDENING
Objective:
- Stabilize the research engine for deterministic experiment execution and reproducible ranking outputs.

Definition of Done (explicit, testable):
- Experiment manifests are produced for all research runs.
- `run_id` is a deterministic hash of inputs and config artifacts.
- Parameter sweep and result comparison workflows are reproducible.
- Re-running the same experiment inputs produces the same ranking outputs.

Active Constraints:
- No strategy mutation is allowed mid-run.
- No hidden randomness is allowed in experiment execution.
- Every experiment must be reproducible from recorded artifacts.

Transition Gate:
- Identical experiment inputs yield identical rankings and run-identity hashes.

### S4_RISK_ENGINE_MATURITY
Objective:
- Mature the risk engine with hard caps, veto controls, and deterministic freeze behavior.

Definition of Done (explicit, testable):
- Hard limits are enforced for position size, notional, and drawdown.
- Funding shock and volatility expansion guards are enforced.
- Risk veto checks run before simulated order placement.
- Risk blocks and kill-switch activations are emitted as artifacts.
- Kill-switch deterministically freezes runtime under breach conditions.

Active Constraints:
- Risk controls fail-closed on missing data, contract violations, or invariant breaches.
- No production execution connector behavior is enabled in this stage.

Transition Gate:
- Risk breach simulation suite and kill-switch integration tests pass.

### S5_EXECUTION_CONNECTOR_FUTURE
Objective:
- Future stage reserved for controlled execution connector implementation after shadow-mode evidence is sufficient.

Definition of Done (explicit, testable):
- Not active. Criteria will be defined only after S4 completion evidence is accepted.

Active Constraints:
- Connector implementation is deferred and out of current scope.

Transition Gate:
- Formal stage-entry decision recorded after S4 readiness evidence.

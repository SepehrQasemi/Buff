CURRENT_STAGE=S0_REFOUNDATION
NEXT_STAGE_CANDIDATE=S1_ONLINE_DATA_PLANE
OPEN_PRS_TO_DECIDE=0
LAST_RESET_DATE_UTC=2026-02-24
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

CURRENT_STAGE=S0_REFOUNDATION
NEXT_STAGE_CANDIDATE=S1_ONLINE_DATA_PLANE
OPEN_PRS_TO_DECIDE=0
LAST_RESET_DATE_UTC=2026-02-24
STAGE_LADDER=S0_REFOUNDATION|S1_ONLINE_DATA_PLANE|S2_PAPER_LIVE_FUTURES|S3_RESEARCH_ENGINE_HARDENING|S4_RISK_ENGINE_MATURITY|S5_EXECUTION_CONNECTOR_FUTURE
OPS_COMMAND_SOURCE=docs/05_RUNBOOK_DEV_WORKFLOW.md

---

## Current Stage
S0_REFOUNDATION

## Current Objective
Refound Buff as a crypto futures R&D platform with a mandatory online data plane, deterministic artifact truth, realistic paper-live futures simulation, and deferred execution connector scope.

## Active Constraints
- Runtime safety is fail-closed by default.
- Deterministic artifact contracts are mandatory.
- Online data collection is in scope; live order execution is not.
- No production broker connector implementation in the current stage.

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
- Operationalize a disciplined research loop from backtest to walk-forward to paper-live promotion.

Definition of Done (explicit, testable):
- Backtest, walk-forward, and paper-live results are linked through canonical experiment lineage.
- Regime split and cost sensitivity checks are mandatory pre-promotion requirements.
- Promotion/rollback/stop conditions are artifact-tracked and enforceable.

Active Constraints:
- Promotion decisions remain research-governed and fail-closed on missing evidence.
- No live connector enablement in this stage.

Transition Gate:
- Promotion rules execute automatically on artifacts and block candidates that violate stop conditions.

### S4_RISK_ENGINE_MATURITY
Objective:
- Define and validate deterministic decision generation against non-deterministic external execution observations in shadow mode.

Definition of Done (explicit, testable):
- Shadow mode contract records deterministic Decision and observed ExecutionResult separately.
- Reconciliation engine detects drift/mismatch and emits freeze signals.
- Freeze-on-mismatch policy blocks connector progression when reconciliation breaks.

Active Constraints:
- Shadow mode is analysis and reconciliation only; no production order routing.

Transition Gate:
- Reconciliation/freeze behavior is proven under induced mismatch scenarios.

### S5_EXECUTION_CONNECTOR_FUTURE
Objective:
- Future stage reserved for controlled execution connector implementation after shadow-mode evidence is sufficient.

Definition of Done (explicit, testable):
- Not active. Criteria will be defined only after S4 completion evidence is accepted.

Active Constraints:
- Connector implementation is deferred and out of current scope.

Transition Gate:
- Formal stage-entry decision recorded after S4 readiness evidence.

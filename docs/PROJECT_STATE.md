CURRENT_STAGE=S1_ONLINE_DATA_PLANE
NEXT_STAGE_CANDIDATE=S2_PAPER_LIVE_FUTURES
OPEN_PRS_TO_DECIDE=0
LAST_RESET_DATE_UTC=2026-02-24
LAST_VERIFIED_COMMIT=3495d9f9370ef9ae237502dfc46157d665642256
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

CURRENT_STAGE=S1_ONLINE_DATA_PLANE
NEXT_STAGE_CANDIDATE=S2_PAPER_LIVE_FUTURES
OPEN_PRS_TO_DECIDE=0
LAST_RESET_DATE_UTC=2026-02-24
LAST_VERIFIED_COMMIT=3495d9f9370ef9ae237502dfc46157d665642256
STAGE_LADDER=S0_REFOUNDATION|S1_ONLINE_DATA_PLANE|S2_PAPER_LIVE_FUTURES|S3_RESEARCH_ENGINE_HARDENING|S4_RISK_ENGINE_MATURITY|S5_EXECUTION_CONNECTOR_FUTURE
OPS_COMMAND_SOURCE=docs/05_RUNBOOK_DEV_WORKFLOW.md

---

## Current Stage
S1_ONLINE_DATA_PLANE

## Current Objective
Implement the online data plane with immutable raw capture, deterministic canonicalization, and artifacted gap/late/revision fail-closed policies.

## Active Constraints
- Runtime safety is fail-closed by default.
- Deterministic artifact contracts are mandatory.
- Canonicalization must be driven only from raw logs.
- Online data collection is in scope; live order execution is not.
- No production broker connector implementation in the current stage.

## S1 Acceptance Evidence
- PR #300 merged on main: https://github.com/Buff-Trading-AI/Buff/pull/300
- Required tests passed: `test_replay_determinism`, `test_gap_detection_fail_closed`, `test_late_event_policy`
- Canonical artifact digests (sha256):
  - `canonical_events.jsonl`: `89ec575b01decc77c427d0a7112dc7a9af6bf8f354397b505002d9693cefae30`
  - `canonical_ohlcv.jsonl`: `0aa7c8a691c745adc768e72d628fade1500f07be1a82f632519e8b7b41ba5968`
  - `gap_status.json`: `fbd5a2af09df4a02c87d80dec4892ebeb99e71dd7f585cdd91d754104dbf700a`
  - `revision_status.json`: `7fe0b3ed15f8f53b574dec3a0919fa07b4937e24cccd97366e495db4a2a63610`
  - `manifest.json`: `027d77f633dd37ead1d4eda5368a203c68585f920deef0a4072f72f8afda89de`
- Release-gate passed on main commit `3495d9f9370ef9ae237502dfc46157d665642256`:
  https://github.com/Buff-Trading-AI/Buff/actions/runs/22390630290

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

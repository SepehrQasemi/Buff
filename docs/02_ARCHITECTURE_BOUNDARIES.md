# 02_ARCHITECTURE_BOUNDARIES

## Scope
This document defines system boundaries for Buff's futures R&D direction.
Current stage is defined only in `docs/PROJECT_STATE.md`.

## Boundary 1: Data Plane vs Decision Plane
- Online data collection is mandatory.
- Data plane responsibilities end at deterministic canonical market artifacts.
- Data plane has no strategy decision authority and no execution authority.

## Boundary 2: Deterministic Decision Core
- Decision generation must be reproducible from canonical inputs.
- Equivalent inputs must produce equivalent decision artifacts and stable digests.
- Silent mutation of decision artifacts is forbidden.

## Boundary 3: Paper-Live Simulation Authority
- Paper-live futures simulation is the primary runtime mode for execution-like validation.
- Simulation must model realistic costs and risk constraints.
- Simulation runtime remains fail-closed on missing/invalid dependencies.

## Boundary 4: Safety and Fail-Closed Behavior
- Integrity failures, schema violations, and unresolved mismatches block progression.
- Kill-switch semantics are mandatory in paper-live runtime.
- Safety gates override throughput goals.

## Boundary 5: Future Execution Connector Isolation
- Execution connector implementation is deferred.
- Any future connector path must remain isolated from deterministic decision generation.
- Shadow-mode reconciliation evidence is required before connector activation.

## Boundary 6: Artifact Truth
- Artifact records are the only source of runtime truth.
- UI, reporting, and research promotion logic must consume artifacts, not hidden recomputation.

## Canonical Companions
- Contracts: `docs/03_CONTRACTS_AND_SCHEMAS.md`
- Runbook: `docs/05_RUNBOOK_DEV_WORKFLOW.md`
- Online data plane spec: `docs/06_DATA_PLANE_ONLINE.md`
- Paper-live futures spec: `docs/07_PAPER_LIVE_FUTURES.md`
- Research loop spec: `docs/08_RESEARCH_LOOP.md`
- Future execution design: `docs/09_EXECUTION_FUTURE.md`

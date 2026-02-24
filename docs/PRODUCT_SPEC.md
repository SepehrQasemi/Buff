# PRODUCT_SPEC - Buff Futures Research Platform

## Stage Source
Current stage is defined only in `docs/PROJECT_STATE.md`.
This file defines product identity and operating intent, not stage authority.

## Product Identity
Buff is a crypto futures R&D platform built for:
- Mandatory online market data ingestion
- Deterministic artifact-driven research workflows
- Realistic paper-live futures simulation
- Safety-first, fail-closed runtime behavior

Buff is not limited to static read-only analysis. The core product direction is research-to-paper-live operation over real online data, with execution connector work deferred until proven.

## Product Mandates

### 1) Online Data Is Mandatory
- Research and paper-live workflows must run on online market data collection.
- Data ingestion must be resilient (websocket primary, REST fallback) and reproducible via artifacts.

### 2) Deterministic Artifact Truth
- Canonical artifacts are the source of truth for evaluation, comparison, and replay.
- Equivalent inputs must produce equivalent canonical outputs and stable digests.

### 3) Paper-Live Is Primary Runtime Mode
- Paper-live futures simulation is the primary execution-like mode for validation.
- Paper-live must include realistic baseline cost/risk mechanics (fees, funding, slippage, liquidation safeguards).

### 4) Execution Connector Is Deferred
- Real exchange order routing is intentionally deferred to a future stage.
- No current-stage claim implies production execution readiness.

## Core Principles
- Safety-first: fail closed on invalid inputs, integrity failures, policy violations, or unresolved mismatches.
- Determinism-first: no hidden nondeterministic paths in decision generation.
- Provenance-first: every decision/result is traceable through versioned artifacts.
- Separation of concerns: data plane, simulation plane, and future execution connector boundaries remain explicit.

## Product Scope (Current Direction)
- Online futures data plane with immutable raw events and canonical market series.
- Backtest and walk-forward experimentation linked to paper-live progression.
- Realistic paper-live futures simulation with risk hard stops and replay guarantees.
- Research promotion loop with explicit pass/fail evidence from artifacts.

## Out Of Scope (Current Stage)
- Live broker/exchange connector operation.
- Production order placement.
- Claims of execution readiness without shadow/reconciliation proof.

## Safety And Risk Expectations
- Hard risk caps and kill-switch semantics are mandatory in simulation runtime.
- Policy failures, data corruption, and digest mismatches block progression automatically.
- Promotion to later stages requires explicit evidence gates, not manual optimism.

## Relationship To Supporting Specs
- Data plane contract: `docs/06_DATA_PLANE_ONLINE.md`
- Paper-live futures contract: `docs/07_PAPER_LIVE_FUTURES.md`
- Research progression contract: `docs/08_RESEARCH_LOOP.md`
- Future execution design boundary: `docs/09_EXECUTION_FUTURE.md`

# MASTER DEVELOPMENT PATH — Buff Futures R&D Engine

Status: Canonical Development Blueprint  
Authority: Architectural (non-runtime)  
Last Updated: 2026-02-24  

---

# 1. Mission

Build a deterministic crypto futures R&D platform with:

- Mandatory online data plane
- Raw feed capture before transformation
- Deterministic replay guarantees
- Realistic paper-live futures simulation
- Strict risk enforcement boundaries
- Shadow execution before real execution
- Execution connector strictly deferred to final stage

This document defines the only allowed development order.

---

# 2. Global Non-Negotiable Invariants

These apply to ALL stages:

1. Determinism:
   Identical inputs must produce identical artifacts.

2. Replay Integrity:
   Raw feed → canonicalization → simulation must be reproducible.

3. No Hidden State:
   No runtime behavior may depend on wall-clock time unless explicitly recorded.

4. Artifact Completeness:
   Every run must produce:
   - manifest.json
   - input_digest.json
   - metrics.json
   - decision_log.jsonl
   - trade_log.jsonl (if applicable)

5. No Broker Integration Before S5.

6. No Live Keys Stored Before S5.

7. No Execution Endpoint Exposed Before Shadow Mode Exists.

8. Online ingestion must log RAW exchange responses before parsing.

Violation of any invariant = HARD STOP.

---

# 3. Stage Ladder (Immutable Order)

S0_REFOUNDATION  
S1_ONLINE_DATA_PLANE  
S2_PAPER_LIVE_FUTURES  
S3_RESEARCH_ENGINE_HARDENING  
S4_RISK_ENGINE_MATURITY  
S5_EXECUTION_CONNECTOR_FUTURE  

Stages may NOT be reordered.
No skipping allowed.

---

# 4. Stage Definitions

---

## S0_REFOUNDATION

Objective:
- Clean canonical docs
- Define contracts
- Establish stage ladder
- Eliminate legacy authority conflicts

Non-Goals:
- No runtime expansion
- No broker work
- No websocket client

Exit Gate:
- Single canonical stage authority
- No legacy stage tokens active
- Docs structure coherent

---

## S1_ONLINE_DATA_PLANE

Objective:
- Implement exchange data ingestion (HTTP first, websocket optional)
- RAW feed capture layer (immutable JSONL)
- Canonical candle builder
- Deterministic storage format

Required Components:
- raw_feed_log/
- canonical_candles/
- ingestion manifest
- gap detection policy
- retry + idempotency

Hard Constraints:
- All exchange responses stored before parsing
- No simulation coupling yet
- No strategy execution from live stream

Exit Gate:
- Given identical raw logs → identical canonical candles
- Gap detection test suite passes
- Deterministic replay test passes

---

## S2_PAPER_LIVE_FUTURES

Objective:
- Event-driven simulation loop
- Realistic futures semantics:
  - leverage
  - margin
  - liquidation
  - funding rate
  - slippage
  - partial fills
  - latency model

Required Components:
- exchange-time scheduler
- order book abstraction
- fill engine
- funding accrual model
- liquidation engine

Hard Constraints:
- Simulation driven ONLY from canonical data
- No direct exchange calls
- All decisions logged

Exit Gate:
- 30-day replay deterministic
- Liquidation model unit tested
- Funding model validated
- Position PnL reproducible

---

## S3_RESEARCH_ENGINE_HARDENING

Objective:
- Strategy registry stabilization
- Parameter sweep engine
- Cross-validation artifacts
- Run reproducibility hashing

Required Components:
- experiment manifest
- run_id = deterministic hash(inputs)
- parameter grid runner
- result comparison tool

Hard Constraints:
- No strategy mutation mid-run
- No hidden randomness
- Every experiment reproducible

Exit Gate:
- Same experiment → same ranking
- Hash-based run identity enforced

---

## S4_RISK_ENGINE_MATURITY

Objective:
- Hard risk caps
- Pre-trade veto layer
- Post-trade exposure enforcement
- Kill-switch mechanism

Required Components:
- max_position_size
- max_notional
- max_drawdown_guard
- funding shock guard
- volatility expansion guard

Hard Constraints:
- Risk veto precedes order placement
- Risk blocks must generate artifact entries
- Kill-switch must freeze engine deterministically

Exit Gate:
- Risk breach simulation suite passes
- Kill-switch integration test passes

---

## S5_EXECUTION_CONNECTOR_FUTURE

Objective:
- Broker adapter layer
- Authenticated order lifecycle
- Shadow mode
- Divergence monitoring

Hard Constraints:
- Execution ONLY after shadow validation
- Shadow divergence threshold defined
- Live execution kill-switch mandatory

Non-Goals:
- No auto-enable execution
- No default live mode

Exit Gate:
- 90-day shadow stability
- Divergence < defined threshold
- Risk engine integrated with live adapter

---

# 5. Cross-Stage Dependency Map

S1 required for S2  
S2 required for S4  
S3 depends on S2  
S4 required for S5  

No direct S1 → S5 jump allowed.

---

# 6. Forbidden Moves

- Implementing CCXT live trading before S5
- Generating AI strategies before deterministic replay is proven
- Introducing async behavior without logging event order
- Skipping raw feed storage
- Allowing execution endpoints before shadow mode
- Mixing runtime and docs lanes in one PR

---

# 7. Project Completion Definition

Project considered execution-ready only when:

- 90-day shadow replay stable
- Liquidation validated
- Funding drift validated
- Risk kill-switch tested
- Deterministic replay validated under load

Until then:
System remains research-only.

---

END OF FILE.
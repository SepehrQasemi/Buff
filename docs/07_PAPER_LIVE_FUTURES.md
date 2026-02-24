# 07_PAPER_LIVE_FUTURES

## Purpose
Define Buff's primary paper-live futures simulation contract.

## Decision Timing
Decision timing is bar-close driven.

Rules:
- Strategy and risk evaluation occur only at bar close for the configured timeframe.
- Orders are simulated against the next executable market state according to configured fill policy.
- No intra-bar discretionary decision mutation.

## Fee Model Baseline
Baseline fee model must be explicit and artifact-recorded.

Minimum requirements:
- Maker/taker fee rates configurable per symbol class
- Fee charged per fill notional
- Fee currency handling defined (quote-denominated baseline)
- Fee assumptions included in run manifest

## Funding Model (Futures)
Funding is mandatory in paper-live futures simulation.

Baseline requirements:
- Funding interval schedule is explicit and versioned
- Funding transfer applied to open positions at schedule boundaries
- Funding source data provenance is artifact-recorded
- Missing funding input triggers fail-closed behavior for affected periods

## Slippage Model Baseline
Slippage must be modeled even in baseline mode.

Minimum requirements:
- Deterministic baseline slippage function by side and notional bucket
- Configurable stress multiplier for sensitivity tests
- Slippage assumptions versioned in run artifacts

## Position Model
Paper-live position model must include:
- Isolated position accounting per symbol
- Quantity, average entry, unrealized/realized PnL
- Leverage and maintenance threshold tracking
- Explicit handling of reduce-only behavior in simulation decisions

## Conservative Liquidation Model
Liquidation model must be conservative by design.

Rules:
- If margin health crosses conservative liquidation threshold, position is forcibly flattened in simulation.
- Liquidation events are explicitly labeled and never hidden under normal exits.
- Liquidation threshold config is versioned and artifact-recorded.

## Risk Kill-Switch Rules
Kill-switch is mandatory and fail-closed.

Minimum triggers:
- Hard loss cap breach
- Repeated model/execution mismatch in simulation pipeline
- Data integrity/digest mismatch in active session
- Manual operator kill-switch activation

Kill-switch behavior:
- Block new entries immediately
- Force safe-state for open-risk expansion
- Emit explicit kill-switch artifact event with reason code

## Required Artifacts
Each paper-live run must produce at least:
- `paper_run_manifest.json`
- `decision_records.jsonl`
- `simulated_orders.jsonl`
- `simulated_fills.jsonl`
- `position_timeline.jsonl`
- `risk_events.jsonl`
- `cost_breakdown.json`
- `funding_transfers.jsonl`
- `run_digests.json`

## Replay Guarantee
Paper-live replay must be reproducible for fixed inputs.

Replay identity includes at minimum:
- Canonical market data digest
- Strategy/version/config digest
- Risk config digest
- Fee/slippage/funding model version identifiers
- Seed (if stochastic components are enabled)

Acceptance condition:
- Replaying the same identity tuple yields matching decision and artifact digests.

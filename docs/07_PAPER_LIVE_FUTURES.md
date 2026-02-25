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
Successful runs must produce:
- `paper_run_manifest.json`
- `decision_records.jsonl`
- `simulated_orders.jsonl`
- `simulated_fills.jsonl`
- `position_timeline.jsonl`
- `risk_events.jsonl`
- `cost_breakdown.json`
- `funding_transfers.jsonl`
- `artifact_pack_manifest.json`
- `run_digests.json`

Failed runs must produce:
- `paper_run_manifest.json`
- `risk_events.jsonl`
- `run_failure.json`
- `artifact_pack_manifest.json`
- `run_digests.json`

Rule:
- `run_failure.json` must not exist for successful runs.

## Numeric Policy Contract
S2 numeric serialization is a versioned contract:

- `policy_id`: `s2/numeric/fixed_decimal_8/v1`
- `format`: `fixed_decimal`
- `decimals`: `8`
- `rounding`: `ROUND_HALF_EVEN`

Policy digest:
- `numeric_policy_digest_sha256` is `sha256(canonical_json_bytes(NUMERIC_POLICY))`.
- Canonical JSON encoding uses:
  - `sort_keys=True`
  - `separators=(",", ":")`
  - `ensure_ascii=False`
  - `allow_nan=False`
  - UTF-8 bytes

Artifact requirements:
- Every JSON artifact includes top-level `numeric_policy_id`.
- Every JSONL record includes `numeric_policy_id`.
- Missing or mismatched `numeric_policy_id` fails closed with `SCHEMA_INVALID`.

## Structured Failure Contract
S2 failure artifacts use:
- `s2/error/v1`
- `s2/run_failure/v1`

`run_failure.json` validation contract:
- Top-level required by validator: `schema_version`, `numeric_policy_id`, `error`
- `error` required/validated fields:
  - `schema_version` must be `s2/error/v1`
  - `numeric_policy_id` must match active numeric policy
  - `error_code` must be in allowed set
  - `severity` must be `FATAL`
  - `source` must include `component`, `stage`, `function`
  - `timestamp` must be canonical UTC string

Allowed error codes:
- `ARTIFACT_MISSING`
- `DATA_INTEGRITY_FAILURE`
- `DIGEST_MISMATCH`
- `INPUT_DIGEST_MISMATCH`
- `INPUT_INVALID`
- `INPUT_MISSING`
- `MISSING_CRITICAL_FUNDING_WINDOW`
- `ORDERING_INVALID`
- `SCHEMA_INVALID`
- `SIMULATION_FAILED`

Precedence contract (`resolve_error_code`):
1. `SCHEMA_INVALID`
2. `ARTIFACT_MISSING`
3. `DIGEST_MISMATCH`
4. `INPUT_DIGEST_MISMATCH`
5. `INPUT_MISSING`
6. `INPUT_INVALID`
7. `MISSING_CRITICAL_FUNDING_WINDOW`
8. `DATA_INTEGRITY_FAILURE`
9. `ORDERING_INVALID`
10. `SIMULATION_FAILED`

Deterministic failure timestamp rule:
- Normalize candidate timestamps to canonical UTC.
- Use lexicographically earliest normalized candidate.
- If no candidate exists, use fallback `1970-01-01T00:00:00Z`.

## Artifact Validation Order
Validation order is strict:
1. Validate encoding + parse `artifact_pack_manifest.json` and `run_digests.json`
2. Verify file hashes and root hash
3. Parse and validate remaining artifact semantics

Behavioral consequence:
- Tampered artifact bytes without digest recompute fail as `DIGEST_MISMATCH`.
- If digests are recomputed after tampering, semantic invalidity can fail as `SCHEMA_INVALID`.

Float token policy:
- Any parsed JSON/JSONL float token fails closed with `SCHEMA_INVALID` and message
  `artifact contains non-canonical float token`.

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

## How To Verify S2 Locally
Run from repository root:

```bash
python -m ruff format .
python -m ruff check .
python -m pytest -q
python -m tools.release_gate --strict --timeout-seconds 900
python -m pytest -q tools/test_s2_double_run_compare.py tools/test_s2_artifact_pack_completeness.py
```

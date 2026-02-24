ARCHIVED — NOT AUTHORITATIVE
Superseded by new documentation reset 2026-02-24.
Do not rely on this file for current stage or product direction.

# Selector Contract

## Overview
The selector contract defines deterministic inputs and outputs for strategy selection.
It guarantees that identical inputs produce identical outputs and audit hashes.

## SelectorInput (schema_version=1)
Required fields:
- schema_version: `1`
- market_state: mapping with deterministic keys/values
- risk_state: string (e.g., `GREEN`, `YELLOW`, `RED`)
- allowed_strategy_ids: stable list of allowed strategy IDs
- constraints: mapping of selector constraints (optional; default empty)

Optional fields:
- timeframe
- snapshot_hash
- universe (sorted list of symbols)

Canonicalization uses `audit.canonical_json` for stable bytes.

## SelectorOutput (schema_version=1)
Fields:
- schema_version: `1`
- chosen_strategy_id: string or null
- chosen_strategy_version: int or null
- reason_codes: stable ordered list of strings
- audit_fields: deterministic mapping of decision facts
- tie_break: explicit tie-break rule string

## Ordering + Tie-break rules
Selection is deterministic and uses:
1) highest score (descending)
2) strategy_id (lexicographic ascending)
3) version (descending)

Tie-break rule string: `score_desc_strategy_id_asc_version_desc`.

## Reason codes
Examples:
- `rule:R0` / `rule:R1` / `rule:R2` / `rule:R3` / `rule:R9`
- `best_score`
- `tie_break_strategy_id`
- `no_selection`

## Error semantics
- `selector_schema_version_invalid`
- `selector_market_state_invalid`
- `selector_risk_state_invalid`
- `selector_allowed_strategies_invalid`
- `selector_constraints_invalid`
- `selector_strategy_id_invalid`
- `selector_strategy_version_invalid`
- `selector_reason_codes_invalid`
- `selector_audit_fields_invalid`
- `selector_tie_break_invalid`
- `selector_unknown_strategy` (unregistered or unknown strategy_id)
- `selector_strategy_not_registered` (registry validation failed)
- `selector_strategy_disallowed` (risk_state not allowed)
- `selector_score_override_invalid`

## Determinism guarantee
- Canonicalized selector inputs/outputs produce stable hashes.
- Stable ordering and explicit tie-break rules.
- No randomness, no IO, no external state.

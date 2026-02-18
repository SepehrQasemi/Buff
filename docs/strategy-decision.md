# Strategy Decision Contract

## Decision schema (schema_version=1)
Fields:
- schema_version: `1`
- as_of_utc: ISO-8601 UTC timestamp
- instrument: symbol string
- action: `HOLD | ENTER_LONG | EXIT_LONG | ENTER_SHORT | EXIT_SHORT`
- rationale: ordered list of short reason codes
- risk:
  - max_position_size
  - stop_loss
  - take_profit
  - policy_ref (optional)
- provenance:
  - feature_bundle_fingerprint
  - strategy_id (`name@version`)
  - strategy_params_hash
- confidence (optional): 0.0-1.0

## Invariants
- Deterministic outputs for identical inputs.
- Schema-versioned validation with fail-closed errors.
- No order placement or live trading in strategy execution.
- No silent fallback; all violations raise errors.
- Reproducibility core: the full decision payload is deterministic for identical inputs.

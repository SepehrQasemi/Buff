# RISK_POLICY

## Risk State
- green: normal
- yellow: reduce size or restrict new positions
- red: no-trade (hard stop)

## Hard Limits (default v1.0)
- Max exposure: configured per account (fail-closed if missing)
- Max trades/day: configured per account (fail-closed if missing)
- Leverage cap: configured per account (fail-closed if missing)

## Evidence Requirements
- Data and feature snapshots must be hashed
- Risk decision must be recorded with reasons and thresholds

## Hard Rule
- risk_state = red -> NO TRADE

This layer is permission-only and must not generate directional signals.

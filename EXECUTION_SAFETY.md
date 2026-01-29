# EXECUTION_SAFETY

## Idempotency
- Execution must be idempotent by event_id and intent_id.
- Duplicate events must not create duplicate orders.

## Position State Machine
- FLAT -> OPENING -> OPEN -> CLOSING -> FLAT
- Partial fills must be handled deterministically.

## Kill Switch
- Kill switch blocks all new orders immediately.
- Existing positions must only be reduced or closed.

## API Failure Behavior
- Any API or network failure -> safe state (no new orders).
- Missing or invalid inputs -> block execution.

## Protective Exit
- All live orders require a protective exit flag (SL/TP or bracket).

## Secrets Handling
- API keys from environment variables only.
- Never commit secrets or .env files.

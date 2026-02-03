# EXECUTION_SAFETY

## Idempotency
- Execution must be idempotent by event_id and intent_id.
- Duplicate events must not create duplicate orders.

### Idempotency Inflight (Broker Error Fail-Closed)
- Trigger: any broker/API exception during order submission leaves the idempotency key in **INFLIGHT**.
- Rationale: fail-closed safety; we do **not** auto-finalize or clear on broker error to avoid duplicate or out-of-order execution.
- Operator resolution (manual):
  1) Stop the paper/live runner.
  2) Inspect decision records for broker errors:
     - `workspaces/<run_id>/decision_records.jsonl` (paper execution) fields:
       - `execution_status` = `ERROR`
       - `reason` starts with `broker_error:`
  3) Resolve broker/API issue.
  4) Clear the idempotency record:
     - Default DB: `workspaces/idempotency.sqlite` (override via `BUFF_IDEMPOTENCY_DB_PATH`).
     - To reset everything (safe for paper only): delete `workspaces/idempotency.sqlite`.
     - To surgically clear one key: use `sqlite3` and delete the row in `idempotency_records` by key.
  5) Re-run the intent once the idempotency store is cleared.

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

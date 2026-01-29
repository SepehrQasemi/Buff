# DECISION_RECORD_SCHEMA

Each execution decision is appended as one JSON object per line in decision_records.jsonl.

## Required Fields
- record_version: int
- decision_id: str
- timestamp: ISO-8601 string
- event_id: str
- intent_id: str
- strategy_id: str
- risk_state: str (GREEN/YELLOW/RED)
- permission: str (ALLOW/RESTRICT/BLOCK)
- action: str (blocked/placed/noop/duplicate)
- reason: str
- data_snapshot_hash: str
- feature_snapshot_hash: str
- execution:
    - order_ids: list[str]
    - filled_qty: float
    - status: str

## Optional Fields
- notes: str
- metadata: dict

## Contract Goals
- Supports full replay and post-mortem audit.
- Deterministic and append-only.

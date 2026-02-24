ARCHIVED — NOT AUTHORITATIVE
Superseded by new documentation reset 2026-02-24.
Do not rely on this file for current stage or product direction.

# Chatbot

Phase-0 product behavior for the chatbot is defined in `docs/CHATBOT_SPEC.md`. This document describes the current read-only artifact reporting implementation.

## Architecture
- Intent router selects one of: reporting, auditing, teaching (`src/chatbot/router.py`).
- Safety guard blocks execution/broker/order requests (`src/chatbot/tools/safety_guard.py`).
- Read-only loaders handle JSON/text/parquet (`src/chatbot/tools/load_artifact.py`, `src/chatbot/tools/query_parquet.py`).
- Orchestrator assembles deterministic responses (`src/chatbot/chatbot.py`).
- Reporting daily summary consumes `trades.parquet`, `selector_trace.json`, and `reports/risk_timeline.json`.

## Examples
- Reporting: "daily summary" -> reads `workspaces/<run_id>/trades.parquet`, `workspaces/<run_id>/selector_trace.json`, `reports/risk_timeline.json`.
- Auditing: "audit runs" -> reads `workspaces/index.json`.
- Teaching: "teach chatbot" -> reads `docs/chatbot.md`.

## How to generate daily summary
Required artifacts:
- `workspaces/<run_id>/trades.parquet`
- `workspaces/<run_id>/selector_trace.json`
- `reports/risk_timeline.json`

Use the canonical daily-summary command from the runbook and replace `RUN_ID` there.
See [Runbook: Chatbot Operations](./05_RUNBOOK_DEV_WORKFLOW.md#chatbot-operations).

## Non-capabilities
- No order placement, broker execution, or control-plane actions.
- No mutation of artifacts; all responses are read-only.
- No summaries when required artifacts are missing (returns "unknown").
- No invention or extrapolation beyond provided artifacts.


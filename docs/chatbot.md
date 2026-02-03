# Chatbot

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

## Non-capabilities
- No order placement, broker execution, or control-plane actions.
- No mutation of artifacts; all responses are read-only.
- No summaries when required artifacts are missing (returns "unknown").
- No invention or extrapolation beyond provided artifacts.

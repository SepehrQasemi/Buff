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

Command (replace `RUN_ID`):
```bash
python -c "from pathlib import Path; from chatbot import Chatbot, ChatbotConfig; run_id='RUN_ID'; cfg=ChatbotConfig(root_dir=Path('.'), trades_path=Path(f'workspaces/{run_id}/trades.parquet'), selector_trace_path=Path(f'workspaces/{run_id}/selector_trace.json'), risk_timeline_path=Path('reports/risk_timeline.json')); Path('reports/daily_summary.md').write_text(Chatbot(cfg).respond('daily summary'), encoding='utf-8')"
```

## Non-capabilities
- No order placement, broker execution, or control-plane actions.
- No mutation of artifacts; all responses are read-only.
- No summaries when required artifacts are missing (returns "unknown").
- No invention or extrapolation beyond provided artifacts.



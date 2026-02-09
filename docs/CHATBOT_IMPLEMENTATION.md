# CHATBOT_IMPLEMENTATION

## API Endpoints
- GET /api/v1/chat/modes returns supported modes with required and optional context fields.
- POST /api/v1/chat accepts { mode, message, context }.

## Request Example
```
POST /api/v1/chat
{
  "mode": "add_indicator",
  "message": "add an RSI indicator",
  "context": {
    "indicator_id": "simple_rsi",
    "name": "Simple RSI",
    "inputs": ["close"],
    "outputs": ["rsi"]
  }
}
```

## Response Shape
```
{
  "mode": "...",
  "title": "...",
  "summary": "...",
  "steps": [{"id": "...", "text": "..."}],
  "files_to_create": [{"path": "...", "contents": "..."}],
  "commands": ["..."],
  "success_criteria": ["..."],
  "warnings": ["..."],
  "blockers": ["..."],
  "diagnostics": {"inputs": {...}, "notes": ["..."]}
}
```

## Mode Behavior
- add_indicator: returns indicator.yaml and indicator.py templates plus validation commands.
- add_strategy: returns strategy.yaml and strategy.py templates plus governance warnings.
- review_plugin: reads plugin files and returns blockers/warnings/suggestions in steps.
- explain_trade: explains based on artifacts only (decision records + trades if present).

## Fail-Closed Behavior
If required artifacts are missing for review_plugin/explain_trade:
- blockers includes "insufficient_artifacts"
- files_to_create is empty
- steps include exact commands to generate the required artifacts

## UI Wiring
Chart Workspace -> AI Chat tab calls GET /api/v1/chat/modes and POST /api/v1/chat.
The panel renders structured responses and remains read-only (no execution triggers).

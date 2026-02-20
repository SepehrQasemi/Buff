# CHATBOT_SPEC — AI Assistant (Guide + Reviewer)

## Purpose
The chatbot helps users:
- add strategies and indicators safely
- understand required steps and files
- validate and fix errors
- review strategy/indicator for common pitfalls

Chatbot is an assistant, not an execution controller.

## Contract And Safety Constraints
- Chatbot responses are advisory only.
- Chatbot MUST NOT bypass the `/api/v1/runs` validation path.
- Chatbot MUST NOT initiate or execute trades.
- Chatbot MUST NOT mutate artifacts directly.
- Any run creation requested through chatbot MUST call the same validated API endpoints used by the UI.
- Canonical contract reference: [03_CONTRACTS_AND_SCHEMAS.md](./03_CONTRACTS_AND_SCHEMAS.md).

## Modes
### Draft Mode (Default)
Chatbot outputs:
- templates (code + yaml)
- step-by-step instructions
- validation commands to run
It does not silently modify system behavior.

### Review Mode
Chatbot reads artifacts and provides analysis:
- suspicious lookahead/leakage patterns
- NaN/warmup issues
- overfitting smells
- inconsistency warnings

### Explain Mode
Given a trade marker or run_id:
- explains why trade happened
- references decision/timeline events and parameter settings

## Flow 1: Add Indicator
Inputs from user:
- name/id
- input series (close/high/low/volume)
- outputs (names)
- params + defaults + ranges
- warmup bars
- nan_policy

Chatbot output:
- Folder layout to create:
  - user_indicators/<id>/{indicator.yaml, indicator.py, tests/...}
- Template code and yaml
- Checklist:
  - run validate
  - run tests
  - open UI ? indicator appears

## Flow 2: Add Strategy
Inputs from user:
- name/id
- rules: entry/exit conditions
- required indicators
- params schema
- warmup bars
- optional confidence logic

Chatbot output:
- Folder layout:
  - user_strategies/<id>/{strategy.yaml, strategy.py, tests/...}
- Template code and yaml
- Example config + UI steps:
  - select strategy
  - set params
  - run and visualize

## Flow 3: Review Strategy/Indicator
Chatbot checks and reports:
- Contract compliance
- Causality / lookahead suspicion:
  - usage of future-looking windows or index shifts
- Warmup and NaN handling
- Excessive parameterization (overfit risk)
- Unclear rules (suggest clarification in README)

Outputs:
- A structured report:
  - Issues (blockers)
  - Warnings
  - Suggestions
  - Next tests to run

## Flow 4: Troubleshoot Errors
Given an error message or validation output:
- identify likely root cause
- propose specific edits
- propose commands to re-run validation and tests

## S7 Research Assistant Mode
Purpose:
- Provide artifact-grounded research analysis for single-user experiment workflows.

Mode boundaries:
- Chat is NOT an execution layer.
- Chat analyzes artifacts only.
- Chat must not mutate runs, experiments, or runtime state.
- Chat must preserve deterministic interpretation rules and must not invent missing inputs.

Research inputs:
- `metrics.json`
- `trades.jsonl`
- `timeline.json`
- experiment metadata and ranking artifacts when present

Research outputs:
- run-to-run comparison summaries grounded in provided artifacts
- drawdown and trade-pattern diagnostics with explicit evidence references
- next-parameter-test suggestions framed as hypotheses, not guarantees
- uncertainty notices when required artifacts are missing or invalid

## Non-negotiable Safety Rules
Chatbot must not:
- instruct users to disable hard risk caps
- claim profitability guarantees
- recommend live deployment actions
- circumvent validation gates

## “Exact Steps” Requirement
When user asks “I want to add X” the chatbot must respond with:
1) exact files to create
2) exact fields to fill
3) exact commands to run
4) what success looks like in UI


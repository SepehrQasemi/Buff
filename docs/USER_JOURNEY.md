---
# User Journey (Official)

This document describes the smallest complete user journey that must always work.

## Journey 1 — Create a run and inspect results

### Preconditions
- The user has a CSV file containing historical candles (OHLCV) in the expected format.
- The user has selected a strategy (built-in or approved plugin).

### Steps
1) Open the UI run creation page.
2) Select a CSV file (file picker).

**Current status note**
If the current UI implementation uses a path field rather than file selection, treat it as a temporary implementation detail.
The target user experience is file-based selection. See `docs/DECISIONS.md` (D-001).

3) Select a strategy and parameters.
4) Start creation.
5) The UI shows progress and returns a run id.
6) The run appears in the run list.
7) Open the run workspace page and inspect:
   - Chart candles and markers
   - Trades (if produced)
   - Metrics
   - Timeline / decision records (as artifacts)

### Success Criteria
- Run id is deterministic for the same canonical inputs.
- Artifacts are written under the runs root.
- Workspace renders strictly from artifacts (no hidden recompute).

## Journey 2 — Reproduce the same run
1) Use the same CSV + same parameters again (UI or CLI).
2) The resulting run id matches the previous one.
3) Workspace renders identical results.

## Journey 3 — Error recovery (must be user-explainable)
The UI must show a clear action for each case:
- Runs root missing/misconfigured → show how to configure it
- CSV invalid/unreadable → show what is wrong
- Strategy/indicator validation fails → show which file/field failed
- Run already exists → treat as success or show idempotent message
- Network/API unreachable → show retry guidance

## Notes on file-based data input
The UI uses file selection. Internally, the backend may store the file and reference it as a controlled internal path so request contracts can remain path-based.
---







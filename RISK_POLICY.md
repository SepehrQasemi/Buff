# RISK_POLICY

## Purpose
This layer provides a deterministic, explainable permission-to-trade state (green/yellow/red).
This layer is permission-only: it does not predict direction and does not select strategies.

## States and sizing
- green: normal permission, size_multiplier = 1.0
- yellow: permission with reduced risk, size_multiplier = 0.5
- red: no-trade, size_multiplier = 0.0

## Windows and cooldown (v1)
- Pre-window: 2 hours before event time
- Post-window: 2 hours after event time
- High severity cooldown: 4 hours after event time

## Parameter names (current defaults)
- WINDOW_PRE = 2 hours
- WINDOW_POST = 2 hours
- HIGH_COOLDOWN = 4 hours
- SIZE_MULTIPLIER_GREEN = 1.0
- SIZE_MULTIPLIER_YELLOW = 0.5
- SIZE_MULTIPLIER_RED = 0.0

## Rule summary (deterministic)
- High severity events within the window -> red
- High severity cooldown after the event -> red
- Medium severity events within the window -> yellow
- Otherwise -> green
- Low severity events do not change the state

## Explainability requirements
Every output includes:
- reasons: list of strings explaining which rule fired
- event_ids: list of source event IDs used for the decision

## Example
Example A (single high severity event):
- evt_high_20260110_1200 @ 2026-01-10T12:00:00+00:00 (high, macro)
Sample hourly outputs:
- 2026-01-10T10:00:00+00:00 -> red (within window of evt_high_20260110_1200)
- 2026-01-10T15:00:00+00:00 -> red (cooldown after evt_high_20260110_1200)
- 2026-01-10T17:00:00+00:00 -> green

Example B (single medium severity event):
- evt_med_20260110_1500 @ 2026-01-10T15:00:00+00:00 (medium, earnings)
Sample hourly outputs:
- 2026-01-10T13:00:00+00:00 -> yellow (within window of evt_med_20260110_1500)
- 2026-01-10T18:00:00+00:00 -> green

## CLI example
python -m src.risk.cli --events tests/fixtures/risk_events.json --start 2026-01-10T08:00:00Z --end 2026-01-10T20:00:00Z --out reports/risk_timeline.json

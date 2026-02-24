ARCHIVED — NOT AUTHORITATIVE
Superseded by new documentation reset 2026-02-24.
Do not rely on this file for current stage or product direction.

# Goldens

Golden indicator outputs live at `tests/goldens/expected.csv`.

## Purpose

- Deterministic, preset-only expected values.
- Used by tests to validate indicator math and runner output.

## Rules

- Do not regenerate goldens unless the preset specification changes.
- Goldens are limited to the supported presets only.
- All comparisons use strict tolerances with NaN-aware equality.

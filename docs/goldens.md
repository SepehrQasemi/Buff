# Goldens

Golden indicator outputs live at `tests/goldens/expected.csv`.

## Purpose

- Deterministic, preset-only expected values.
- Used by tests to validate indicator math and runner output.

## Rules

- Do not regenerate goldens unless the preset specification changes.
- Goldens are limited to the supported presets only.
- All comparisons use strict tolerances with NaN-aware equality.

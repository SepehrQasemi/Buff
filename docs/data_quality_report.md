# Data Quality Report (1m)

This report is a deterministic workspace artifact written as
`workspaces/<run_id>/data_quality.json` when `--run_id` is supplied to the
ingest CLI.

## Scope

The report evaluates **only the canonical 1m OHLCV** dataset and enforces
strict UTC 1-minute grid assumptions. It does **not** resample or fill gaps.

## Schema (stable, versioned)

Top-level fields:

- `schema_version`: integer (currently `1`)
- `generated_at_utc`: ISO8601 UTC string (deterministically derived from `end_ts`)
- `symbol`: string
- `timeframe`: `"1m"`
- `expected_interval_seconds`: `60`
- `start_ts`: ISO8601 UTC string (first timestamp)
- `end_ts`: ISO8601 UTC string (last timestamp)
- `overall_status`: `"PASS" | "WARN" | "FAIL"`
- `summary`:
  - `counts_by_severity`: `{PASS: int, WARN: int, FAIL: int}` (counts of checks by severity)
  - `counts_by_check`: `{gaps: int, duplicates: int, out_of_order: int, zero_volume: int}`
- `findings`: list of deterministic findings

Finding fields:

- `check_id`: `"gaps" | "duplicates" | "out_of_order" | "zero_volume"`
- `severity`: `"WARN" | "FAIL"`
- `start_ts`: ISO8601 UTC string or empty
- `end_ts`: ISO8601 UTC string or empty
- `code`: stable code (`missing_timestamp`, `duplicate_timestamp`, `out_of_order`, `zero_volume`)

Findings are **sorted deterministically** by `(check_id, start_ts, end_ts, code)`.

## Severity rules

- `gaps`: **FAIL** if any missing 1m timestamps
- `duplicates`: **FAIL** if any duplicate timestamps
- `out_of_order`: **FAIL** if timestamps are non-monotonic
- `zero_volume`: **WARN** if any zero-volume candles

## Determinism guarantee

For identical input data, the report is byte-for-byte identical:

- stable JSON key ordering
- stable findings ordering
- deterministic `generated_at_utc` (derived from `end_ts`)

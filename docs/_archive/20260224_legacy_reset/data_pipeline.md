ARCHIVED — NOT AUTHORITATIVE
Superseded by new documentation reset 2026-02-24.
Do not rely on this file for current stage or product direction.

# Data Pipeline (M1)

This milestone builds a canonical, deterministic 1m OHLCV dataset for Binance USDT-M Futures.

For derived timeframes, see `docs/data_timeframes.md`. The multi-timeframe runner
(`src/buff/data/run_ingest.py`) resamples from 1m and writes partitioned outputs.

## Run

Use the canonical ingest command from the runbook to generate deterministic 1m data artifacts.
See [Runbook: Data Pipeline Operations](./05_RUNBOOK_DEV_WORKFLOW.md#data-pipeline-operations).

## Artifacts

- Parquet: `data/ohlcv_1m/{SYMBOL}.parquet`
- Report: `.tmp_report/data_quality.json`

## Invariants

- Timeframe is fixed to `1m`.
- UTC everywhere; timestamps are epoch milliseconds aligned to minute boundaries.
- Strict validation: gaps, duplicates, misalignment, zero volume, or candle integrity violations fail.
- Deterministic storage: sorted by `["symbol", "timestamp"]`, stable schema, `zstd` compression.

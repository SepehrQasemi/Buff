# Data Timeframes

This document defines the canonical timeframe rules for Buff. The base ingest is 1m; all higher
intervals are deterministic resamples from 1m.

## Canonical Base Timeframe
- **Base timeframe**: 1m (ingest only).
  Evidence: `src/data/ingest.py`, `src/buff/data/run_ingest.py`, `src/ta/timeframes.py`.
- **Derived timeframes**: fixed-duration and calendar-based intervals derived from 1m.
  Evidence: `src/buff/data/resample.py`, `src/ta/timeframes.py`.

## Supported Timeframes
- **Fixed-duration**: `5m, 15m, 30m, 1h, 2h, 4h, 1d, 1w, 2w`.
  Evidence: `src/buff/data/resample.py` (`FIXED_TIMEFRAMES_MINUTES`).
- **Calendar-based**: `1M, 3M, 6M, 1Y`.
  Evidence: `src/buff/data/resample.py` (`CALENDAR_TIMEFRAMES`).
- **1m passthrough**: 1m data may be returned unchanged as the base dataset.
  Evidence: `src/buff/data/resample.py` (`resample_ohlcv`).

## OHLCV Aggregation Rules (Resampling)
For every derived candle:
- `open` = first open in the window
- `high` = max high in the window
- `low` = min low in the window
- `close` = last close in the window
- `volume` = sum of volumes in the window

Evidence: `src/buff/data/resample.py` (`_aggregate_ohlcv`), `tests/test_resample.py`.

## Candle Timestamp Convention
- Derived candle timestamp is the **window start** (left label).
- Resampling uses left-closed, left-labeled windows.

Evidence: `src/buff/data/resample.py` (`resample_fixed`, `resample_calendar` use `label="left"`, `closed="left"`).

## Handling of Gaps
- **1m ingest is strict**: gaps, duplicates, misalignment, zero volume, and OHLCV integrity violations fail validation.
  Evidence: `src/data/validate.py`, `tests/test_data_m1_validation.py`.
- **Resampling does not fill gaps**: derived candles are computed from available data only.
  Missing windows show up as missing bars in data quality reports.
  Evidence: `src/buff/data/resample.py`, `src/buff/data/report.py`, `tests/test_resample.py`.

## Partial Windows
- **Fixed-duration** windows: if the last window has fewer than the expected 1m bars, it is dropped.
  Evidence: `src/buff/data/resample.py` (`resample_fixed`, `counts < minutes`).
- **Calendar-based** windows: the final bucket is dropped if it does not include the last minute of the window.
  Evidence: `src/buff/data/resample.py` (`resample_calendar`, `bucket_end - 1 minute`).

## Timezone Requirements
- All timestamps are treated as UTC.
- 1m ingest uses epoch milliseconds aligned to exact minute boundaries.
- Derived timeframes expect `ts` as timezone-aware UTC timestamps.

Evidence: `src/data/ingest.py`, `src/data/validate.py`, `src/buff/data/report.py`.

## Deterministic Constraints
- Inputs are sorted by timestamp before resampling; outputs are stable and reproducible.
  Evidence: `src/buff/data/resample.py`, `tests/test_resample.py`.
- Canonical 1m parquet writes are deterministic in schema and ordering.
  Evidence: `src/data/store.py`, `tests/test_data_m1_reproducibility.py`.

## Implementation References
- Resampling entrypoint: `src/buff/data/resample.py` (`resample_ohlcv`, `resample_fixed`, `resample_calendar`).
- Multi-timeframe ingest runner: `src/buff/data/run_ingest.py` (enforces base_timeframe=1m).
- Canonical 1m ingest: `src/data/ingest.py` + `src/data/validate.py` + `src/data/store.py`.
- Data quality reporting: `src/buff/data/report.py`, `schemas/data_quality.schema.json`.

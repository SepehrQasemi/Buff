# Deterministic 1m Resampling

This document defines the deterministic resampling contract for canonical 1m OHLCV.

## Input schema

Required columns:
- `ts` (UTC timestamp, minute-aligned)
- `open`, `high`, `low`, `close`, `volume`

Input must be:
- strictly monotonic by `ts`
- free of duplicate timestamps

## Window alignment

Windows are aligned to **UTC epoch** boundaries. Each window is:
- **left-closed, right-open**
- timestamped by the **window start**

Example for 5-minute (`300` seconds) windows:
- `00:00:00`–`00:04:59` → window start `00:00:00`
- `00:05:00`–`00:09:59` → window start `00:05:00`

## Aggregation rules

For each window:
- `open`   = first open in the window
- `high`   = max high in the window
- `low`    = min low in the window
- `close`  = last close in the window
- `volume` = sum(volume)

## Completeness rule (no lookahead)

Incomplete windows are **dropped**. A window is complete only if it contains
exactly `timeframe_seconds / 60` one‑minute bars.

This prevents lookahead: truncating future minutes removes or changes the final bar.

## Determinism

Given identical input, the output is byte‑for‑byte identical:
- stable ordering
- no randomness
- no implicit time dependencies

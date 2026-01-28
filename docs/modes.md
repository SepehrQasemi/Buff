# Modes: Manual vs System

## Shared Layer

Only the following are shared across modes:

- Market data reads (OHLCV/timeframes)
- Indicator/timeframe DEFINITIONS ONLY (formulas/registry; no params/state)

## Manual Analysis Mode

- Read-only market data
- Write ONLY to: `workspaces/`
- Forbidden: writing to `features/`, `reports/`, `logs/`
- Forbidden: influencing system decisions or configs

## System/Core Mode

- Read market data + versioned system configs
- Write ONLY to: `features/`, `reports/`, `logs/`
- Forbidden: reading anything from `workspaces/`
- Forbidden: using manual/user configs

Rule:

"No shared state, no shared config, no shared outputs."

## Runner Modes (Train vs Live)

The feature runner supports a separate notion of mode:

- train (default): identical to the legacy behavior, no trimming.
- live: no trimming, output length equals input length, warmup NaNs preserved.

These runner modes are independent of the Manual/System architecture modes above.

Example (expected behavior):

```text
train: output length == input length, warmup NaNs preserved
live:  output length == input length, warmup NaNs preserved
```

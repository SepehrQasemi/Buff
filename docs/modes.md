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

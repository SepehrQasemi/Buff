ARCHIVED — NOT AUTHORITATIVE
Superseded by new documentation reset 2026-02-24.
Do not rely on this file for current stage or product direction.

# Risk Permission Layer (M4)

## Purpose
The risk permission layer is a deterministic gate that consumes precomputed features
and raw OHLCV and outputs a permission decision. It does **not** generate directional
signals or execute trades.
Phase-0 product scope exposes 5 risk levels (1..5) as UI presets; this document describes the internal GREEN/YELLOW/RED permission layer evaluated within a selected level.

## Inputs
- ATR feature (default: `atr_14`)
- Close prices
- Timestamps (must be monotonic increasing and unique)

## Derived Metrics
- `atr_pct = atr / close`
- `realized_vol = rolling std of log returns` over a fixed window

## Default Configuration
- `realized_vol_window`: 20
- `missing_lookback`: 10
- `max_missing_fraction`: 0.20
- `yellow_atr_pct`: 0.01
- `red_atr_pct`: 0.02
- `yellow_vol`: 0.01
- `red_vol`: 0.02
- `recommended_scale_yellow`: 0.25

All thresholds live in `RiskConfig` (`src/risk/types.py`) and are deterministic.

## Decision Rules
1) **RED** if any of:
   - index is invalid (no timestamp/ts and no DatetimeIndex)
   - timestamps are invalid (not monotonic or duplicated)
   - close contains NaN/<=0
   - missing_fraction > max_missing_fraction (computed over `missing_lookback`)
   - latest atr_pct or realized_vol is missing
   - atr_pct > red_atr_pct
   - realized_vol > red_vol
2) **YELLOW** if not RED and any of:
   - atr_pct between yellow_atr_pct and red_atr_pct (inclusive)
   - realized_vol between yellow_vol and red_vol (inclusive)
3) **GREEN** otherwise.

## Outputs
- `risk_state`: GREEN / YELLOW / RED
- `permission`: ALLOW / RESTRICT / BLOCK
- `recommended_scale`: 1.0 (GREEN), 0.25 (YELLOW), 0.0 (RED)
- `reasons`: list of rule labels that triggered the decision
- `metrics`: latest atr_pct, realized_vol, thresholds, timestamps

## Auditing
Every run writes a deterministic JSON report to:
- Manual mode: `workspaces/<workspace>/reports/risk_report.json`
- System mode: `reports/risk_report.json`

Reports include inputs, thresholds, and timestamps to support reproducibility.

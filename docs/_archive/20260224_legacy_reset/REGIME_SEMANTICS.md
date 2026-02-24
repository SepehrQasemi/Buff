ARCHIVED — NOT AUTHORITATIVE
Superseded by new documentation reset 2026-02-24.
Do not rely on this file for current stage or product direction.

# Regime Semantics

Regime semantics provide a deterministic permission layer. A regime is not a buy/sell signal; it only gates which strategy families are allowed to run.

## Regimes (7)
- RISK_OFF
- HIGH_VOL_TREND
- LOW_VOL_TREND
- HIGH_VOL_RANGE
- LOW_VOL_RANGE
- MEAN_REVERSION_BIAS
- NEUTRAL

## Default thresholds (conservative, not optimized)
- adx_trend_threshold: 25
- adx_range_threshold: 20
- high_atr_pct_threshold: 0.02
- low_atr_pct_threshold: 0.01
- realized_vol_high_threshold: 0.03
- realized_vol_low_threshold: 0.015
- risk_off_atr_pct_threshold: 0.03
- risk_off_realized_vol_threshold: 0.05

These are defaults used in `knowledge/regimes.yaml`. They are not tuned and should be revisited for new markets or timeframes.

## Fail-closed rules
- Missing required features (or NaNs) return `RISK_OFF` with `missing_features` in the summary.
- No silent defaults are applied during evaluation.

## Adding a new regime safely
1) Add the regime to `knowledge/regimes.yaml` with a unique priority.
2) Keep priorities strictly descending; `RISK_OFF` must be highest and `NEUTRAL` must be lowest.
3) Use numeric, unambiguous conditions and only approved feature names.
4) Update tests in `tests/unit` and add at least one explicit classification example.
5) Re-run `ruff` and `pytest`.

## Feature references
Regime conditions must reference known indicator outputs and derived risk metrics, including:
- adx_14, atr_pct, realized_vol_20 (alias: realized_vol)
- rsi_14, rsi_slope_14_5
- ema_spread_20_50
- vwap_typical_daily
- bb_upper_20_2, bb_lower_20_2

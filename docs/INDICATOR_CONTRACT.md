# INDICATOR_CONTRACT — Built-in and User-defined Indicators

## Contract Alignment
- All numeric handling MUST align with deterministic backend policy.
- Validation errors MUST propagate as canonical error codes defined in [03_CONTRACTS_AND_SCHEMAS.md#error-code-registry](./03_CONTRACTS_AND_SCHEMAS.md#error-code-registry).
- This specification is descriptive and MUST NOT override runtime contract enforcement.

## Purpose
Indicators are reusable computations that produce series used in strategies and overlays.
Indicators must be:
- causal (no future access)
- deterministic
- pure (no side effects)

## Indicator Definition
Indicator = Pure function:
- inputs: one or more series (close/high/low/volume) + params
- outputs: one or more series

## Required Files (User Indicators)
- `user_indicators/<indicator_id>/indicator.yaml`
- `user_indicators/<indicator_id>/indicator.py`
- `user_indicators/<indicator_id>/tests/test_indicator.py` (recommended)

## indicator.yaml
Must include:
- id, name, version, author (optional)
- category: trend/momentum/volatility/volume/statistics/structure
- inputs:
  - required series list (e.g., close, high, low)
- outputs:
  - output series names (e.g., rsi, upper, lower)
- params schema:
  - type, default, min/max/enum, description
- warmup_bars: integer
- nan_policy: one of:
  - "propagate" (NaNs until enough bars)
  - "fill" (fill with default after warmup, discouraged)
  - "error" (fail if NaNs appear after warmup)

## indicator.py Interface
- `def get_schema() -> dict`
- `def compute(ctx) -> dict`
  ctx provides:
  - input series up to current bar (no future)
  - params
  returns dict mapping output series name -> value (or series update)

## Causality Rules
Indicator must only use data at or before the current bar.
No forward-looking rolling windows that peek into future.

## Validation Requirements
Indicator is loadable only if:
- schema valid
- compute returns expected output keys
- warmup_bars honored
- nan_policy obeyed
- forbidden imports/ops not used

## Built-in Indicator Coverage (v1 expectation)
The built-in library should cover:
- Moving averages: SMA, EMA, WMA, RMA, HMA, VWMA
- Momentum: RSI, MACD, Stoch, ROC, CCI
- Volatility: ATR, Bollinger Bands, Keltner Channels
- Trend strength: ADX/DMI
- Volume: OBV, VWAP, MFI
- Statistics: rolling mean/std, z-score, percentiles
- Structure: pivots, swing high/low

## Canonical contract constants
```text
ALLOWED_PARAM_TYPES: ["int", "float", "bool", "string", "enum"]
ALLOWED_NAN_POLICIES: ["propagate", "fill", "error"]
ALLOWED_INTENTS: ["HOLD", "ENTER_LONG", "ENTER_SHORT", "EXIT_LONG", "EXIT_SHORT"]
```
These constants are shared by indicator and strategy contracts.

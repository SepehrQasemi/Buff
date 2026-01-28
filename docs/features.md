# Feature Engine (M4.1 / M4.2)

This document defines the feature engine contract for deterministic indicator computation.

## Registry Structure

Each preset is defined in the registry as a dict with:

- requires: list of required input columns (e.g., ["close"])
- func: callable that computes the indicator
- params: parameter dict passed to func
- outputs: list of output column names for the preset

## Multi-Output Mapping Rules

- If func returns a Series, it is written to outputs[0].
- If func returns a DataFrame, its columns are renamed to outputs in order.
- Output column order is deterministic and follows the registry order.

## Warmup and NaN Policy

All presets preserve warmup NaNs. The runner does not trim rows.
The first reliable index per preset is recorded as valid_from.

## Validity Metadata

Validity is stored without changing the metadata schema:

feature_params[preset]["_valid_from"] = <int index>

valid_from is the first index where the feature becomes reliable. For MACD,
valid_from is warmup-1.

## Presets

Legacy presets:
- ema_20 -> outputs: ema_20 (period=20)
- rsi_14 -> outputs: rsi_14 (period=14)
- atr_14 -> outputs: atr_14 (period=14)

Tier-1 presets:
- sma_20 -> outputs: sma_20 (period=20)
- std_20 -> outputs: std_20 (period=20, ddof=0)
- bbands_20_2 -> outputs: bb_mid_20_2, bb_upper_20_2, bb_lower_20_2 (period=20, k=2.0, ddof=0)
- macd_12_26_9 -> outputs: macd_12_26_9, macd_signal_12_26_9, macd_hist_12_26_9 (fast=12, slow=26, signal=9)

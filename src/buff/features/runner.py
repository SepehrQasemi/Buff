"""Feature runner for deterministic feature computation."""

from __future__ import annotations

import pandas as pd

from buff.features.registry import FEATURES


REQUIRED_INPUT_COLUMNS = ["timestamp", "open", "high", "low", "close"]
OUTPUT_COLUMNS = ["ema_20", "rsi_14", "atr_14"]


def run_features(df: pd.DataFrame) -> pd.DataFrame:
    missing = [col for col in REQUIRED_INPUT_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    input_df = df.copy()
    input_df = input_df.sort_values("timestamp").reset_index(drop=True)

    features = {}
    for name in OUTPUT_COLUMNS:
        spec = FEATURES[name]
        features[name] = spec["callable"](input_df)

    out = pd.DataFrame(features)
    out.index = pd.to_datetime(input_df["timestamp"], utc=True)
    out = out[OUTPUT_COLUMNS]
    return out

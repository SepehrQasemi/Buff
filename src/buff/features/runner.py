"""Feature runner for deterministic feature computation."""

from __future__ import annotations

import pandas as pd

from buff.data.contracts import validate_ohlcv
from buff.features.registry import FEATURES


OUTPUT_COLUMNS = ["ema_20", "rsi_14", "atr_14"]


def run_features(df: pd.DataFrame) -> pd.DataFrame:
    input_df = validate_ohlcv(df)

    features = {}
    for name in OUTPUT_COLUMNS:
        spec = FEATURES[name]
        features[name] = spec["callable"](input_df)

    out = pd.DataFrame(features)
    out.index = input_df.index
    out = out[OUTPUT_COLUMNS]
    return out

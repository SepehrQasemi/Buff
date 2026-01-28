"""Feature runner for deterministic feature computation."""

from __future__ import annotations

import pandas as pd

from buff.data.contracts import validate_ohlcv
from buff.features.registry import FEATURES


def run_features(df: pd.DataFrame) -> pd.DataFrame:
    input_df = validate_ohlcv(df)

    features: dict[str, pd.Series] = {}
    output_columns: list[str] = []

    for name, spec in FEATURES.items():
        for col in spec["requires"]:
            if col not in input_df.columns:
                raise ValueError(f"Missing required column for {name}: {col}")
        result = spec["func"](input_df, **spec["params"])
        outputs = spec["outputs"]
        if isinstance(result, pd.Series):
            features[outputs[0]] = result
            output_columns.append(outputs[0])
        elif isinstance(result, pd.DataFrame):
            if len(outputs) != len(result.columns):
                raise ValueError(f"Output column mismatch for {name}")
            renamed = result.copy()
            renamed.columns = outputs
            for col in outputs:
                features[col] = renamed[col]
                output_columns.append(col)
        else:
            raise ValueError(f"Unsupported output type for {name}")

    out = pd.DataFrame(features)
    out.index = input_df.index
    out = out[output_columns]
    return out

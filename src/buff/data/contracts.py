"""Data contracts for OHLCV inputs."""

from __future__ import annotations

import pandas as pd


REQUIRED_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def validate_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    data = df.copy()
    timestamps = pd.to_datetime(data["timestamp"], errors="coerce", utc=True)
    if timestamps.isna().any():
        raise ValueError("Invalid timestamp values")
    if timestamps.duplicated().any():
        raise ValueError("Duplicate timestamps are not allowed")
    if not timestamps.is_monotonic_increasing:
        raise ValueError("Timestamps must be monotonic increasing")
    data["timestamp"] = timestamps

    for col in ["open", "high", "low", "close", "volume"]:
        numeric = pd.to_numeric(data[col], errors="coerce")
        if numeric.isna().any():
            raise ValueError(f"Non-numeric or NaN values found in '{col}'")
        data[col] = numeric.astype(float)

    out = data[REQUIRED_COLUMNS].copy()
    out = out.sort_values("timestamp")
    out.index = out["timestamp"]
    out = out.drop(columns=["timestamp"])
    return out

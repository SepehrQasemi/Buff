"""Deterministic 1m OHLCV resampling (no lookahead).

Contract:
- Input must be canonical 1m OHLCV with UTC `ts` column.
- Windows are aligned to UTC epoch (floor to timeframe_seconds).
- Output timestamp is the window start (left-closed, right-open).
- Incomplete windows are dropped (no lookahead).
"""

from __future__ import annotations

from typing import Iterable

import pandas as pd


REQUIRED_COLUMNS = ("ts", "open", "high", "low", "close", "volume")


def _ensure_columns(df: pd.DataFrame, required: Iterable[str]) -> None:
    missing = sorted(set(required) - set(df.columns))
    if missing:
        raise ValueError(f"missing_columns:{missing}")


def _ensure_minute_aligned(ts: pd.Series) -> None:
    if (ts.dt.second != 0).any() or (ts.dt.microsecond != 0).any():
        raise ValueError("timestamps_not_minute_aligned")


def resample_ohlcv(df: pd.DataFrame, timeframe_seconds: int) -> pd.DataFrame:
    if timeframe_seconds <= 0 or timeframe_seconds % 60 != 0:
        raise ValueError("invalid_timeframe_seconds")

    _ensure_columns(df, REQUIRED_COLUMNS)
    if df.empty:
        return pd.DataFrame(columns=list(REQUIRED_COLUMNS))

    ts = pd.to_datetime(df["ts"], utc=True)
    _ensure_minute_aligned(ts)

    if ts.duplicated().any():
        raise ValueError("duplicate_timestamps")
    if not ts.is_monotonic_increasing:
        raise ValueError("timestamps_not_sorted")

    frame = df.copy()
    frame["ts"] = ts

    # Use floor on tz-aware timestamps to avoid dependence on internal time unit
    # (pandas 3.0 defaults can change datetime64 resolution).
    frame["_bucket"] = frame["ts"].dt.floor(f"{timeframe_seconds}s").astype("datetime64[ns, UTC]")

    grouped = frame.groupby("_bucket", sort=True, observed=True)
    aggregated = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        count=("ts", "size"),
    )

    expected_count = timeframe_seconds // 60
    aggregated = aggregated[aggregated["count"] == expected_count].drop(columns=["count"])
    aggregated = aggregated.reset_index().rename(columns={"_bucket": "ts"})

    return aggregated.reset_index(drop=True)

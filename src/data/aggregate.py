"""Aggregation utilities for 1m OHLCV data."""

from __future__ import annotations

import pandas as pd

MS_PER_MINUTE = 60_000
CANONICAL_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume", "symbol"]


def _normalize_resample_rule(timeframe: str) -> str:
    """Normalize timeframe string to a fixed-minute resample rule."""
    try:
        delta = pd.to_timedelta(timeframe)
    except ValueError as exc:
        raise ValueError(f"Invalid timeframe: {timeframe}") from exc

    if delta <= pd.Timedelta(0):
        raise ValueError(f"Timeframe must be positive: {timeframe}")

    minutes = delta.total_seconds() / 60.0
    if minutes < 1 or not minutes.is_integer():
        raise ValueError("Timeframe must be a whole number of minutes.")

    return f"{int(minutes)}min"


def aggregate_ohlcv(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Aggregate 1m OHLCV data into a higher timeframe.

    Args:
        df: DataFrame with 1m data (timestamp in UTC ms).
        timeframe: Target timeframe (e.g., "5m", "15m", "1h").

    Returns:
        Aggregated DataFrame with columns: timestamp, open, high, low, close, volume, symbol.
    """
    if df.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    required = {"timestamp", "open", "high", "low", "close", "volume", "symbol"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    rule = _normalize_resample_rule(timeframe)

    if (df["timestamp"].astype("int64") % MS_PER_MINUTE != 0).any():
        raise ValueError("All timestamps must be minute-aligned for aggregation.")

    frames: list[pd.DataFrame] = []
    for symbol, group in df.groupby("symbol", sort=True):
        ordered = group.sort_values("timestamp").reset_index(drop=True)
        ts_index = pd.to_datetime(ordered["timestamp"].astype("int64"), unit="ms", utc=True)
        ordered = ordered.set_index(ts_index)

        resampled = ordered.resample(rule, label="left", closed="left").agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )

        resampled = resampled.dropna(subset=["open", "high", "low", "close"])
        if resampled.empty:
            continue

        resampled = resampled.reset_index().rename(columns={"index": "timestamp"})
        ts = pd.to_datetime(resampled["timestamp"], utc=True)
        ns = ts.to_numpy(dtype="datetime64[ns]")
        resampled["timestamp"] = (ns.astype("int64") // 1_000_000).astype("int64")
        resampled["symbol"] = symbol

        resampled = resampled[CANONICAL_COLUMNS]
        for col in ["open", "high", "low", "close", "volume"]:
            resampled[col] = resampled[col].astype("float64")
        resampled["symbol"] = resampled["symbol"].astype("string")

        frames.append(resampled)

    if not frames:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    return combined

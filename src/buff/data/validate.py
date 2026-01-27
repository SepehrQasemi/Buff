"""Data quality validation and reporting."""

from dataclasses import dataclass

import pandas as pd


@dataclass
class DataQuality:
    """Data quality metrics with examples for debugging."""

    rows: int
    start_ts: str
    end_ts: str
    duplicates: int
    missing_candles: int
    zero_volume: int
    missing_examples: list[str]  # Up to 5 example timestamps of missing candles
    zero_volume_examples: list[str]  # Up to 5 example timestamps of zero-volume candles


def expected_step_seconds(timeframe: str) -> int:
    """Convert timeframe string to expected step in seconds.

    Args:
        timeframe: Timeframe string (e.g., "1h", "15m", "1d").

    Returns:
        Expected step in seconds.
    """
    multiplier_map = {
        "m": 60,
        "h": 3600,
        "d": 86400,
        "w": 604800,
        "M": 2592000,  # Approximation: 30 days
    }

    if timeframe.endswith("m"):
        minutes = int(timeframe[:-1])
        return minutes * 60
    elif timeframe.endswith("h"):
        hours = int(timeframe[:-1])
        return hours * 3600
    elif timeframe.endswith("d"):
        days = int(timeframe[:-1])
        return days * 86400
    elif timeframe.endswith("w"):
        weeks = int(timeframe[:-1])
        return weeks * 604800
    elif timeframe.endswith("M"):
        months = int(timeframe[:-1])
        return months * 2592000
    else:
        raise ValueError(f"Unknown timeframe: {timeframe}")


def compute_quality(df: pd.DataFrame, timeframe: str) -> DataQuality:
    """Compute data quality metrics for a OHLCV DataFrame.

    Args:
        df: DataFrame with columns ts, open, high, low, close, volume.
               ts must be datetime64[ns, UTC].
        timeframe: Timeframe string (e.g., "1h").

    Returns:
        DataQuality instance with counts and examples.
    """
    rows = len(df)

    if rows == 0:
        return DataQuality(
            rows=0,
            start_ts="",
            end_ts="",
            duplicates=0,
            missing_candles=0,
            zero_volume=0,
            missing_examples=[],
            zero_volume_examples=[],
        )

    start_ts = str(df["ts"].min())
    end_ts = str(df["ts"].max())

    # Count duplicate timestamps (convert numpy.int64 to Python int)
    duplicates = int(df["ts"].duplicated().sum())

    # Count and find zero volume candles
    zero_vol_mask = df["volume"] <= 0
    zero_volume = int(zero_vol_mask.sum())
    zero_volume_examples = [str(ts) for ts in df.loc[zero_vol_mask, "ts"].head(5)]

    # Compute missing candles from gaps and collect examples
    missing_candles = 0
    missing_examples_list = []
    expected_step = expected_step_seconds(timeframe)
    ts_diff = df["ts"].diff().dt.total_seconds()

    # Skip first NaN diff
    for i, diff in enumerate(ts_diff.iloc[1:], start=1):
        if pd.notna(diff) and diff > expected_step:
            # Number of missing candles = gap / expected_step - 1
            num_missing = int((diff / expected_step) - 1)
            missing_candles += num_missing

            # Get the timestamp before the gap
            prev_ts = df["ts"].iloc[i - 1]

            # Generate missing timestamps and collect examples
            for j in range(1, num_missing + 1):
                if len(missing_examples_list) < 5:
                    missing_ts = prev_ts + pd.Timedelta(seconds=j * expected_step)
                    missing_examples_list.append(str(missing_ts))

    return DataQuality(
        rows=rows,
        start_ts=start_ts,
        end_ts=end_ts,
        duplicates=duplicates,
        missing_candles=missing_candles,
        zero_volume=zero_volume,
        missing_examples=missing_examples_list,
        zero_volume_examples=zero_volume_examples,
    )

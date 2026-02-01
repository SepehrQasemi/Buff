"""Validation helpers for canonical OHLCV data."""

from __future__ import annotations

from typing import Iterable, Sequence

import pandas as pd

MS_PER_MINUTE = 60_000


class DataValidationError(Exception):
    """Raised when OHLCV validation fails."""

    def __init__(self, message: str, stats: dict[str, int | float | None] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.stats = stats or {}

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


def _ensure_columns(df: pd.DataFrame, required: Iterable[str]) -> None:
    missing = sorted(set(required) - set(df.columns))
    if missing:
        raise DataValidationError(f"Missing required columns: {missing}")


def _freq_to_ms(expected_freq: str) -> int:
    try:
        delta = pd.to_timedelta(expected_freq)
    except ValueError as exc:
        raise DataValidationError(f"Invalid frequency: {expected_freq}") from exc

    if delta <= pd.Timedelta(0):
        raise DataValidationError(f"Frequency must be positive: {expected_freq}")

    ms = int(delta.total_seconds() * 1000)
    if ms <= 0:
        raise DataValidationError(f"Frequency too small: {expected_freq}")
    return ms


def check_no_duplicates(df: pd.DataFrame, keys: Sequence[str] | None = None) -> int:
    """Raise if duplicates exist for the provided key columns.

    Returns the number of duplicate rows (excluding the first occurrence).
    """
    if keys is None:
        keys = ["symbol", "timestamp"]
    _ensure_columns(df, keys)

    duplicates = df.duplicated(subset=list(keys), keep="first")
    count = int(duplicates.sum())
    if count > 0:
        first = df.loc[duplicates, list(keys)].iloc[0].to_dict()
        raise DataValidationError(
            f"Duplicate rows found for keys {list(keys)}: count={count}, first={first}"
        )
    return count


def check_monotonic_timestamp(df: pd.DataFrame) -> None:
    """Raise if timestamps are not monotonic increasing per symbol (or globally)."""
    _ensure_columns(df, ["timestamp"])
    if df.empty:
        raise DataValidationError("No rows available to check monotonic timestamps.")

    if "symbol" in df.columns:
        for symbol, group in df.groupby("symbol", sort=True):
            if not group["timestamp"].is_monotonic_increasing:
                raise DataValidationError(
                    f"Timestamps are not monotonic increasing for symbol {symbol}."
                )
    else:
        if not df["timestamp"].is_monotonic_increasing:
            raise DataValidationError("Timestamps are not monotonic increasing.")


def check_missing_gaps(
    df: pd.DataFrame,
    expected_freq: str = "1min",
    tolerance: float = 0.001,
) -> dict[str, int | float]:
    """Raise if missing bars exceed tolerance.

    Tolerance is a ratio (0.001 = 0.1%). Missing is computed per symbol using
    the observed min/max timestamps.
    """
    _ensure_columns(df, ["timestamp"])
    if df.empty:
        raise DataValidationError("No rows available to check missing gaps.")

    freq_ms = _freq_to_ms(expected_freq)

    total_missing = 0
    total_expected = 0

    if "symbol" in df.columns:
        groups = df.groupby("symbol", sort=True)
    else:
        groups = [("__all__", df)]

    for symbol, group in groups:
        timestamps = group["timestamp"].dropna().astype("int64").sort_values().drop_duplicates()
        if timestamps.empty:
            raise DataValidationError(f"No timestamps available for symbol {symbol}.")

        start = int(timestamps.iloc[0])
        end = int(timestamps.iloc[-1])
        expected = ((end - start) // freq_ms) + 1
        missing = max(expected - int(timestamps.shape[0]), 0)
        missing_ratio = (missing / expected) if expected > 0 else 0.0

        total_missing += missing
        total_expected += expected

        if missing_ratio > tolerance:
            raise DataValidationError(
                f"Missing ratio {missing_ratio:.6f} exceeds tolerance {tolerance} for symbol {symbol}."
            )

    overall_ratio = (total_missing / total_expected) if total_expected > 0 else 0.0
    return {
        "missing_count": total_missing,
        "expected_count": total_expected,
        "missing_ratio": overall_ratio,
    }


def check_non_negative_volume(df: pd.DataFrame) -> int:
    """Raise if any volume is negative. Returns negative count."""
    _ensure_columns(df, ["volume"])
    if df.empty:
        raise DataValidationError("No rows available to check volume.")

    volume = df["volume"].astype("float64")
    negatives = volume < 0
    count = int(negatives.sum())
    if count > 0:
        first = int(negatives.idxmax())
        raise DataValidationError(f"Negative volume rows found: count={count}, first_index={first}")
    return count


def _empty_stats(start_ms: int, end_ms: int) -> dict[str, int | float | None]:
    expected_rows = (end_ms - start_ms) // MS_PER_MINUTE
    missing_ratio = 1.0 if expected_rows else 0.0
    return {
        "rows": 0,
        "start_timestamp": None,
        "end_timestamp": None,
        "duplicates_count": 0,
        "gaps_count": expected_rows,
        "missing_ratio": missing_ratio,
        "negative_volume_rows": 0,
        "zero_volume_rows": 0,
        "misaligned_rows": 0,
        "integrity_violations_count": 0,
    }


def validate_1m(df: pd.DataFrame, symbol: str, start_ms: int, end_ms: int) -> dict:
    """Validate a 1m OHLCV DataFrame for a single symbol.

    Args:
        df: DataFrame containing canonical columns.
        symbol: Symbol being validated.
        start_ms: Inclusive range start (ms).
        end_ms: Exclusive range end (ms).

    Returns:
        Stats dict with validation metrics.

    Raises:
        DataValidationError if any invariant is violated.
    """
    required = {"symbol", "timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise DataValidationError(
            f"{symbol} missing required columns: {missing}", _empty_stats(start_ms, end_ms)
        )

    if start_ms % MS_PER_MINUTE != 0 or end_ms % MS_PER_MINUTE != 0:
        raise DataValidationError(
            "Start/end timestamps must be minute-aligned.", _empty_stats(start_ms, end_ms)
        )

    expected_rows = (end_ms - start_ms) // MS_PER_MINUTE
    if expected_rows < 0:
        raise DataValidationError("End must be after start.", _empty_stats(start_ms, end_ms))

    if df.empty:
        stats = _empty_stats(start_ms, end_ms)
        raise DataValidationError(f"{symbol} returned no rows.", stats)

    df_sorted = df.sort_values(["timestamp"]).reset_index(drop=True)
    unique_symbols = set(df_sorted["symbol"].dropna().astype(str).unique())
    if unique_symbols and unique_symbols != {symbol}:
        raise DataValidationError(
            f"{symbol} contains unexpected symbols: {sorted(unique_symbols)}",
            _empty_stats(start_ms, end_ms),
        )

    try:
        timestamps = df_sorted["timestamp"].astype("int64")
    except (TypeError, ValueError) as exc:
        raise DataValidationError(
            f"{symbol} timestamp column must be int64.", _empty_stats(start_ms, end_ms)
        ) from exc

    duplicates_mask = timestamps.duplicated()
    duplicates_count = int(duplicates_mask.sum())

    misaligned_rows = int((timestamps % MS_PER_MINUTE != 0).sum())
    out_of_range = int(((timestamps < start_ms) | (timestamps >= end_ms)).sum())

    in_range_unique = timestamps[(timestamps >= start_ms) & (timestamps < end_ms)]
    in_range_unique = in_range_unique.drop_duplicates().sort_values().reset_index(drop=True)

    gaps_count = 0
    if expected_rows > 0:
        gaps_count = max(expected_rows - int(in_range_unique.shape[0]), 0)

    missing_ratio = (gaps_count / expected_rows) if expected_rows else 0.0

    start_timestamp: int | None
    end_timestamp: int | None
    if in_range_unique.empty:
        start_timestamp = None
        end_timestamp = None
    else:
        start_timestamp = int(in_range_unique.iloc[0])
        end_timestamp = int(in_range_unique.iloc[-1])

    try:
        prices = df_sorted[["open", "high", "low", "close"]].astype("float64")
        volume = df_sorted["volume"].astype("float64")
    except (TypeError, ValueError) as exc:
        raise DataValidationError(
            f"{symbol} price/volume columns must be float64.",
            _empty_stats(start_ms, end_ms),
        ) from exc

    max_oc = prices[["open", "close"]].max(axis=1)
    min_oc = prices[["open", "close"]].min(axis=1)
    integrity_mask = (prices["high"] >= max_oc) & (prices["low"] <= min_oc)
    integrity_mask &= prices["high"] >= prices["low"]
    integrity_violations_count = int((~integrity_mask).sum())
    negative_volume_rows = int((volume < 0).sum())
    zero_volume_rows = int((volume == 0).sum())

    stats = {
        "rows": int(df_sorted.shape[0]),
        "start_timestamp": start_timestamp,
        "end_timestamp": end_timestamp,
        "duplicates_count": duplicates_count,
        "gaps_count": gaps_count,
        "missing_ratio": missing_ratio,
        "negative_volume_rows": negative_volume_rows,
        "zero_volume_rows": zero_volume_rows,
        "misaligned_rows": misaligned_rows,
        "integrity_violations_count": integrity_violations_count,
    }

    violations = {
        "duplicates": duplicates_count,
        "gaps": gaps_count,
        "misaligned": misaligned_rows,
        "negative_volume": negative_volume_rows,
        "integrity": integrity_violations_count,
        "out_of_range": out_of_range,
    }
    if any(value > 0 for value in violations.values()):
        message = (
            f"{symbol} validation failed: "
            f"duplicates={duplicates_count}, gaps={gaps_count}, "
            f"misaligned={misaligned_rows}, negative_volume={negative_volume_rows}, "
            f"integrity={integrity_violations_count}, out_of_range={out_of_range}"
        )
        raise DataValidationError(message, stats)

    return stats

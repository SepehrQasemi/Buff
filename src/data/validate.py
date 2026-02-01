"""Strict validation for canonical 1m OHLCV data."""

from __future__ import annotations

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
    first_duplicate = None
    if duplicates_count > 0:
        first_duplicate = int(timestamps[duplicates_mask].iloc[0])

    misaligned_rows = int((timestamps % MS_PER_MINUTE != 0).sum())
    out_of_range = int(((timestamps < start_ms) | (timestamps >= end_ms)).sum())

    in_range_ts = timestamps[(timestamps >= start_ms) & (timestamps < end_ms)]
    in_range_ts = in_range_ts.sort_values().reset_index(drop=True)
    in_range_unique = in_range_ts.drop_duplicates().reset_index(drop=True)

    gaps_count = 0
    first_gap_pair: tuple[int, int] | None = None
    if expected_rows > 0:
        if in_range_unique.empty:
            gaps_count = expected_rows
            first_gap_pair = (start_ms, start_ms + MS_PER_MINUTE)
        else:
            first_ts = int(in_range_unique.iloc[0])
            last_ts = int(in_range_unique.iloc[-1])
            if first_ts != start_ms:
                missing_start = (first_ts - start_ms) // MS_PER_MINUTE
                gaps_count += int(missing_start)
                first_gap_pair = (start_ms, start_ms + MS_PER_MINUTE)
            expected_last = end_ms - MS_PER_MINUTE
            if last_ts != expected_last:
                missing_end = (expected_last - last_ts) // MS_PER_MINUTE
                gaps_count += int(missing_end)
                if first_gap_pair is None:
                    first_gap_pair = (last_ts, last_ts + MS_PER_MINUTE)

            diffs = in_range_unique.diff().iloc[1:]
            for idx, diff in diffs.items():
                if diff != MS_PER_MINUTE:
                    if diff > MS_PER_MINUTE:
                        gaps_count += int(diff // MS_PER_MINUTE - 1)
                    if first_gap_pair is None:
                        prev_ts = int(in_range_unique.iloc[idx - 1])
                        first_gap_pair = (prev_ts, prev_ts + MS_PER_MINUTE)

    count_mismatch = expected_rows > 0 and len(in_range_unique) != expected_rows
    if count_mismatch and gaps_count == 0:
        gaps_count = max(expected_rows - len(in_range_unique), 0)
        if first_gap_pair is None:
            first_gap_pair = (start_ms, start_ms + MS_PER_MINUTE)

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
    zero_volume_rows = int((volume <= 0).sum())

    stats = {
        "rows": int(df_sorted.shape[0]),
        "start_timestamp": start_timestamp,
        "end_timestamp": end_timestamp,
        "duplicates_count": duplicates_count,
        "gaps_count": gaps_count,
        "missing_ratio": missing_ratio,
        "zero_volume_rows": zero_volume_rows,
        "misaligned_rows": misaligned_rows,
        "integrity_violations_count": integrity_violations_count,
    }

    violations = {
        "duplicates": duplicates_count,
        "gaps": gaps_count,
        "misaligned": misaligned_rows,
        "zero_volume": zero_volume_rows,
        "integrity": integrity_violations_count,
        "out_of_range": out_of_range,
        "count_mismatch": 1 if count_mismatch else 0,
    }
    if any(value > 0 for value in violations.values()):
        detail_parts = []
        if first_duplicate is not None:
            detail_parts.append(f"first_duplicate={first_duplicate}")
        if first_gap_pair is not None:
            detail_parts.append(f"first_gap_pair=({first_gap_pair[0]},{first_gap_pair[1]})")
        detail = f" ({', '.join(detail_parts)})" if detail_parts else ""
        message = (
            f"{symbol} validation failed: "
            f"duplicates={duplicates_count}, gaps={gaps_count}, "
            f"misaligned={misaligned_rows}, zero_volume={zero_volume_rows}, "
            f"integrity={integrity_violations_count}, out_of_range={out_of_range}"
            f"{detail}"
        )
        raise DataValidationError(message, stats)

    return stats

from __future__ import annotations

import pandas as pd
import pytest

from src.data.validate import DataValidationError, validate_1m

MS = 60_000
ALIGNED_START_MS = 1_700_000_000_000 - (1_700_000_000_000 % MS)


def _make_df(start_ms: int, minutes: int, symbol: str = "BTCUSDT") -> pd.DataFrame:
    timestamps = [start_ms + i * MS for i in range(minutes)]
    open_prices = [100.0 + i for i in range(minutes)]
    close_prices = [100.5 + i for i in range(minutes)]
    high_prices = [max(o, c) + 0.5 for o, c in zip(open_prices, close_prices)]
    low_prices = [min(o, c) - 0.5 for o, c in zip(open_prices, close_prices)]
    volume = [1.0 for _ in range(minutes)]
    return pd.DataFrame(
        {
            "symbol": [symbol for _ in range(minutes)],
            "timestamp": timestamps,
            "open": open_prices,
            "high": high_prices,
            "low": low_prices,
            "close": close_prices,
            "volume": volume,
        }
    )


def test_validate_passes_continuous_minutes() -> None:
    start_ms = ALIGNED_START_MS
    df = _make_df(start_ms, 5)
    stats = validate_1m(df, "BTCUSDT", start_ms, start_ms + 5 * MS)
    assert stats["rows"] == 5
    assert stats["gaps_count"] == 0
    assert stats["duplicates_count"] == 0


def test_validate_fails_on_duplicate_timestamp() -> None:
    start_ms = ALIGNED_START_MS
    df = _make_df(start_ms, 3)
    df = pd.concat([df, df.iloc[[1]]], ignore_index=True)
    with pytest.raises(DataValidationError):
        validate_1m(df, "BTCUSDT", start_ms, start_ms + 3 * MS)


def test_validate_fails_on_gap() -> None:
    start_ms = ALIGNED_START_MS
    df = _make_df(start_ms, 4).drop(index=[2]).reset_index(drop=True)
    with pytest.raises(DataValidationError):
        validate_1m(df, "BTCUSDT", start_ms, start_ms + 4 * MS)


def test_validate_fails_on_misaligned_timestamp() -> None:
    start_ms = ALIGNED_START_MS
    df = _make_df(start_ms, 3)
    df.loc[0, "timestamp"] = df.loc[0, "timestamp"] + 1
    with pytest.raises(DataValidationError):
        validate_1m(df, "BTCUSDT", start_ms, start_ms + 3 * MS)


def test_validate_fails_on_zero_volume() -> None:
    start_ms = ALIGNED_START_MS
    df = _make_df(start_ms, 3)
    df.loc[1, "volume"] = 0.0
    with pytest.raises(DataValidationError):
        validate_1m(df, "BTCUSDT", start_ms, start_ms + 3 * MS)


def test_validate_fails_on_integrity_violation() -> None:
    start_ms = ALIGNED_START_MS
    df = _make_df(start_ms, 3)
    df.loc[1, "high"] = df.loc[1, "open"] - 1.0
    with pytest.raises(DataValidationError):
        validate_1m(df, "BTCUSDT", start_ms, start_ms + 3 * MS)

"""Tests for OHLCV data contracts."""

from __future__ import annotations

import pandas as pd
import pytest

from buff.data.contracts import validate_ohlcv


def test_valid_input_passes() -> None:
    df = pd.read_csv("tests/goldens/expected.csv")
    out = validate_ohlcv(df)
    assert out.index.is_monotonic_increasing
    assert list(out.columns) == ["open", "high", "low", "close"]


def test_missing_column_fails() -> None:
    df = pd.read_csv("tests/goldens/expected.csv")
    df = df.drop(columns=["close"])
    with pytest.raises(ValueError):
        validate_ohlcv(df)


def test_bad_dtype_fails() -> None:
    df = pd.read_csv("tests/goldens/expected.csv")
    df.loc[0, "close"] = "bad"
    with pytest.raises(ValueError):
        validate_ohlcv(df)


def test_duplicate_timestamp_fails() -> None:
    df = pd.read_csv("tests/goldens/expected.csv")
    df.loc[1, "timestamp"] = df.loc[0, "timestamp"]
    with pytest.raises(ValueError):
        validate_ohlcv(df)


def test_non_monotonic_timestamp_fails() -> None:
    df = pd.read_csv("tests/goldens/expected.csv")
    df = df.iloc[::-1].reset_index(drop=True)
    with pytest.raises(ValueError):
        validate_ohlcv(df)

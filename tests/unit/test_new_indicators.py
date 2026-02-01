"""Unit tests for new indicator implementations."""

from __future__ import annotations

import numpy as np
import pandas as pd

from buff.features.indicators import (
    adx_wilder,
    ema,
    ema_spread,
    obv,
    roc,
    rsi_slope,
    vwap_typical_daily,
)


def _load_df() -> pd.DataFrame:
    df = pd.read_csv("tests/goldens/expected.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp")
    return df


def _assert_deterministic(series_a: pd.Series, series_b: pd.Series) -> None:
    np.testing.assert_allclose(series_a.to_numpy(), series_b.to_numpy(), equal_nan=True)


def test_ema_50_length_warmup_determinism() -> None:
    df = _load_df()
    out1 = ema(df["close"], period=50)
    out2 = ema(df["close"], period=50)
    assert len(out1) == len(df)
    assert out1.iloc[:49].isna().all()
    assert out1.iloc[49:].notna().any()
    _assert_deterministic(out1, out2)


def test_ema_spread_20_50_length_warmup_determinism() -> None:
    df = _load_df()
    out1 = ema_spread(df["close"], fast=20, slow=50)
    out2 = ema_spread(df["close"], fast=20, slow=50)
    assert len(out1) == len(df)
    assert out1.iloc[:49].isna().all()
    assert out1.iloc[49:].notna().any()
    _assert_deterministic(out1, out2)


def test_rsi_slope_14_5_length_warmup_determinism() -> None:
    df = _load_df()
    out1 = rsi_slope(df["close"], period=14, slope=5)
    out2 = rsi_slope(df["close"], period=14, slope=5)
    assert len(out1) == len(df)
    assert out1.iloc[:18].isna().all()
    assert out1.iloc[18:].notna().any()
    _assert_deterministic(out1, out2)


def test_roc_12_length_warmup_determinism() -> None:
    df = _load_df()
    out1 = roc(df["close"], period=12)
    out2 = roc(df["close"], period=12)
    assert len(out1) == len(df)
    assert out1.iloc[:12].isna().all()
    assert out1.iloc[12:].notna().any()
    _assert_deterministic(out1, out2)


def test_vwap_typical_daily_length_determinism() -> None:
    df = _load_df()
    out1 = vwap_typical_daily(df["high"], df["low"], df["close"], df["volume"])
    out2 = vwap_typical_daily(df["high"], df["low"], df["close"], df["volume"])
    assert len(out1) == len(df)
    assert out1.isna().sum() == 0
    _assert_deterministic(out1, out2)


def test_obv_length_determinism() -> None:
    df = _load_df()
    out1 = obv(df["close"], df["volume"])
    out2 = obv(df["close"], df["volume"])
    assert len(out1) == len(df)
    assert out1.iloc[0] == 0.0
    _assert_deterministic(out1, out2)


def test_adx_14_length_warmup_determinism() -> None:
    df = _load_df()
    out1 = adx_wilder(df["high"], df["low"], df["close"], period=14)
    out2 = adx_wilder(df["high"], df["low"], df["close"], period=14)
    assert len(out1) == len(df)
    assert out1["plus_di"].iloc[:14].isna().all()
    assert out1["minus_di"].iloc[:14].isna().all()
    assert out1["adx"].iloc[:28].isna().all()
    assert out1["adx"].iloc[28:].notna().any()
    _assert_deterministic(out1["plus_di"], out2["plus_di"])
    _assert_deterministic(out1["minus_di"], out2["minus_di"])
    _assert_deterministic(out1["adx"], out2["adx"])

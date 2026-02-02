"""End-to-end feature runner test against goldens."""

import numpy as np
import pandas as pd

from buff.features.runner import run_features


def test_feature_runner_e2e() -> None:
    df = pd.read_csv("tests/goldens/expected.csv")
    out = run_features(df, mode="train")

    assert out.shape[0] == len(df)
    assert list(out.columns) == [
        "plus_di_14",
        "minus_di_14",
        "adx_14",
        "atr_14",
        "bb_mid_20_2",
        "bb_upper_20_2",
        "bb_lower_20_2",
        "ema_20",
        "ema_50",
        "ema_spread_20_50",
        "macd_12_26_9",
        "macd_signal_12_26_9",
        "macd_hist_12_26_9",
        "obv",
        "roc_12",
        "rsi_14",
        "rsi_slope_14_5",
        "sma_20",
        "std_20",
        "vwap_typical_daily",
    ]

    expected = df.set_index(pd.to_datetime(df["timestamp"], utc=True))
    expected = expected[out.columns]
    assert list(out.columns) == list(expected.columns)

    np.testing.assert_allclose(
        out["ema_20"].to_numpy(),
        expected["ema_20"].to_numpy(),
        rtol=1e-6,
        atol=1e-6,
        equal_nan=True,
    )
    np.testing.assert_allclose(
        out["rsi_14"].to_numpy(),
        expected["rsi_14"].to_numpy(),
        rtol=1e-6,
        atol=1e-6,
        equal_nan=True,
    )
    np.testing.assert_allclose(
        out["atr_14"].to_numpy(),
        expected["atr_14"].to_numpy(),
        rtol=1e-6,
        atol=1e-6,
        equal_nan=True,
    )
    np.testing.assert_allclose(
        out["sma_20"].to_numpy(),
        expected["sma_20"].to_numpy(),
        rtol=1e-6,
        atol=1e-6,
        equal_nan=True,
    )
    np.testing.assert_allclose(
        out["std_20"].to_numpy(),
        expected["std_20"].to_numpy(),
        rtol=1e-6,
        atol=1e-6,
        equal_nan=True,
    )
    np.testing.assert_allclose(
        out["bb_mid_20_2"].to_numpy(),
        expected["bb_mid_20_2"].to_numpy(),
        rtol=1e-6,
        atol=1e-6,
        equal_nan=True,
    )
    np.testing.assert_allclose(
        out["bb_upper_20_2"].to_numpy(),
        expected["bb_upper_20_2"].to_numpy(),
        rtol=1e-6,
        atol=1e-6,
        equal_nan=True,
    )
    np.testing.assert_allclose(
        out["bb_lower_20_2"].to_numpy(),
        expected["bb_lower_20_2"].to_numpy(),
        rtol=1e-6,
        atol=1e-6,
        equal_nan=True,
    )
    np.testing.assert_allclose(
        out["macd_12_26_9"].to_numpy(),
        expected["macd_12_26_9"].to_numpy(),
        rtol=1e-6,
        atol=1e-6,
        equal_nan=True,
    )
    np.testing.assert_allclose(
        out["macd_signal_12_26_9"].to_numpy(),
        expected["macd_signal_12_26_9"].to_numpy(),
        rtol=1e-6,
        atol=1e-6,
        equal_nan=True,
    )
    np.testing.assert_allclose(
        out["macd_hist_12_26_9"].to_numpy(),
        expected["macd_hist_12_26_9"].to_numpy(),
        rtol=1e-6,
        atol=1e-6,
        equal_nan=True,
    )
    np.testing.assert_allclose(
        out["ema_50"].to_numpy(),
        expected["ema_50"].to_numpy(),
        rtol=1e-6,
        atol=1e-6,
        equal_nan=True,
    )
    np.testing.assert_allclose(
        out["ema_spread_20_50"].to_numpy(),
        expected["ema_spread_20_50"].to_numpy(),
        rtol=1e-6,
        atol=1e-6,
        equal_nan=True,
    )
    np.testing.assert_allclose(
        out["rsi_slope_14_5"].to_numpy(),
        expected["rsi_slope_14_5"].to_numpy(),
        rtol=1e-6,
        atol=1e-6,
        equal_nan=True,
    )
    np.testing.assert_allclose(
        out["roc_12"].to_numpy(),
        expected["roc_12"].to_numpy(),
        rtol=1e-6,
        atol=1e-6,
        equal_nan=True,
    )
    np.testing.assert_allclose(
        out["vwap_typical_daily"].to_numpy(),
        expected["vwap_typical_daily"].to_numpy(),
        rtol=1e-6,
        atol=1e-6,
        equal_nan=True,
    )
    np.testing.assert_allclose(
        out["obv"].to_numpy(),
        expected["obv"].to_numpy(),
        rtol=1e-6,
        atol=1e-6,
        equal_nan=True,
    )
    np.testing.assert_allclose(
        out["plus_di_14"].to_numpy(),
        expected["plus_di_14"].to_numpy(),
        rtol=1e-6,
        atol=1e-6,
        equal_nan=True,
    )
    np.testing.assert_allclose(
        out["minus_di_14"].to_numpy(),
        expected["minus_di_14"].to_numpy(),
        rtol=1e-6,
        atol=1e-6,
        equal_nan=True,
    )
    np.testing.assert_allclose(
        out["adx_14"].to_numpy(),
        expected["adx_14"].to_numpy(),
        rtol=1e-6,
        atol=1e-6,
        equal_nan=True,
    )

    out_live = run_features(df, mode="live")
    assert list(out_live.columns) == list(expected.columns)
    assert out_live.shape[0] == len(df)
    assert out_live["macd_12_26_9"].iloc[:33].isna().all()
    assert out_live["macd_12_26_9"].iloc[33:].notna().any()
    assert out_live["ema_20"].iloc[:19].isna().all()
    assert out_live["ema_20"].iloc[19:].notna().any()

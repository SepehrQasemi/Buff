"""Sanity checks for golden indicator outputs."""

from pathlib import Path

import numpy as np
import pandas as pd


def test_goldens_sanity() -> None:
    path = Path("tests/goldens/expected.csv")
    df = pd.read_csv(path)

    rsi = df["rsi_14"].dropna()
    assert (rsi >= 0).all() and (rsi <= 100).all()

    ema = df["ema_20"]
    atr = df["atr_14"]
    std = df["std_20"]
    bb_upper = df["bb_upper_20_2"]
    bb_lower = df["bb_lower_20_2"]
    macd = df["macd_12_26_9"]
    macd_signal = df["macd_signal_12_26_9"]
    macd_hist = df["macd_hist_12_26_9"]
    std_valid = df["std_20"].first_valid_index()

    assert ema.dropna().shape[0] > 0
    assert atr.dropna().shape[0] > 0
    assert (atr.dropna() >= 0).all()
    assert (std.dropna() >= 0).all()
    assert (bb_upper.dropna() >= bb_lower.dropna()).all()
    assert macd.dropna().shape[0] > 0
    assert macd_signal.dropna().shape[0] > 0
    assert macd_hist.dropna().shape[0] > 0

    warmup = 34
    for column in ["macd_12_26_9", "macd_signal_12_26_9", "macd_hist_12_26_9"]:
        assert df[column].iloc[: warmup - 1].isna().all()
        assert df[column].iloc[warmup - 1 :].notna().any()

    assert std_valid is not None
    assert std_valid >= 19
    window = df["close"].iloc[std_valid - 19 : std_valid + 1].to_numpy()
    expected_std = np.std(window, ddof=0)
    np.testing.assert_allclose(df["std_20"].iloc[std_valid], expected_std, rtol=1e-12, atol=1e-12)

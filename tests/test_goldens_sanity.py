"""Sanity checks for golden indicator outputs."""

import pandas as pd
from pathlib import Path


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

    assert ema.dropna().shape[0] > 0
    assert atr.dropna().shape[0] > 0
    assert (atr.dropna() >= 0).all()
    assert (std.dropna() >= 0).all()
    assert (bb_upper.dropna() >= bb_lower.dropna()).all()
    assert macd.dropna().shape[0] > 0
    assert macd_signal.dropna().shape[0] > 0
    assert macd_hist.dropna().shape[0] > 0

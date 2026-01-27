"""Compare indicator outputs against goldens."""

import numpy as np
import pandas as pd

from buff.features.indicators import atr_wilder, ema, rsi_wilder


def test_indicators_match_goldens() -> None:
    df = pd.read_csv("tests/goldens/expected.csv")

    close = df["close"]
    high = df["high"]
    low = df["low"]

    ema_20 = ema(close, period=20).to_numpy()
    rsi_14 = rsi_wilder(close, period=14).to_numpy()
    atr_14 = atr_wilder(high, low, close, period=14).to_numpy()

    np.testing.assert_allclose(ema_20, df["ema_20"].to_numpy(), rtol=1e-6, atol=1e-6, equal_nan=True)
    np.testing.assert_allclose(rsi_14, df["rsi_14"].to_numpy(), rtol=1e-6, atol=1e-6, equal_nan=True)
    np.testing.assert_allclose(atr_14, df["atr_14"].to_numpy(), rtol=1e-6, atol=1e-6, equal_nan=True)

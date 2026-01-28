"""Compare indicator outputs against goldens."""

import numpy as np
import pandas as pd

from buff.features.indicators import (
    atr_wilder,
    bollinger_bands,
    ema,
    macd,
    rolling_std,
    rsi_wilder,
    sma,
)


def test_indicators_match_goldens() -> None:
    df = pd.read_csv("tests/goldens/expected.csv")

    close = df["close"]
    high = df["high"]
    low = df["low"]

    ema_20 = ema(close, period=20).to_numpy()
    rsi_14 = rsi_wilder(close, period=14).to_numpy()
    atr_14 = atr_wilder(high, low, close, period=14).to_numpy()
    sma_20 = sma(close, period=20).to_numpy()
    std_20 = rolling_std(close, period=20, ddof=0).to_numpy()
    bb = bollinger_bands(close, period=20, k=2.0, ddof=0)
    macd_df = macd(close, fast=12, slow=26, signal=9)

    np.testing.assert_allclose(ema_20, df["ema_20"].to_numpy(), rtol=1e-6, atol=1e-6, equal_nan=True)
    np.testing.assert_allclose(rsi_14, df["rsi_14"].to_numpy(), rtol=1e-6, atol=1e-6, equal_nan=True)
    np.testing.assert_allclose(atr_14, df["atr_14"].to_numpy(), rtol=1e-6, atol=1e-6, equal_nan=True)
    np.testing.assert_allclose(sma_20, df["sma_20"].to_numpy(), rtol=1e-6, atol=1e-6, equal_nan=True)
    np.testing.assert_allclose(std_20, df["std_20"].to_numpy(), rtol=1e-6, atol=1e-6, equal_nan=True)
    np.testing.assert_allclose(bb["mid"].to_numpy(), df["bb_mid_20_2"].to_numpy(), rtol=1e-6, atol=1e-6, equal_nan=True)
    np.testing.assert_allclose(bb["upper"].to_numpy(), df["bb_upper_20_2"].to_numpy(), rtol=1e-6, atol=1e-6, equal_nan=True)
    np.testing.assert_allclose(bb["lower"].to_numpy(), df["bb_lower_20_2"].to_numpy(), rtol=1e-6, atol=1e-6, equal_nan=True)
    np.testing.assert_allclose(
        macd_df["macd"].to_numpy(),
        df["macd_12_26_9"].to_numpy(),
        rtol=1e-6,
        atol=1e-6,
        equal_nan=True,
    )
    np.testing.assert_allclose(
        macd_df["signal"].to_numpy(),
        df["macd_signal_12_26_9"].to_numpy(),
        rtol=1e-6,
        atol=1e-6,
        equal_nan=True,
    )
    np.testing.assert_allclose(
        macd_df["hist"].to_numpy(),
        df["macd_hist_12_26_9"].to_numpy(),
        rtol=1e-6,
        atol=1e-6,
        equal_nan=True,
    )

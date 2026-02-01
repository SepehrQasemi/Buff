"""Test that golden expected.csv exists and has required columns."""

import pandas as pd
from pathlib import Path


def test_goldens_exist() -> None:
    path = Path("tests/goldens/expected.csv")
    assert path.exists()

    df = pd.read_csv(path)
    assert len(df) >= 150

    base_cols = {
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }
    feature_cols = {
        "adx_14",
        "atr_14",
        "bb_lower_20_2",
        "bb_mid_20_2",
        "bb_upper_20_2",
        "ema_20",
        "ema_50",
        "ema_spread_20_50",
        "macd_12_26_9",
        "macd_hist_12_26_9",
        "macd_signal_12_26_9",
        "minus_di_14",
        "obv",
        "plus_di_14",
        "roc_12",
        "rsi_14",
        "rsi_slope_14_5",
        "sma_20",
        "std_20",
        "vwap_typical_daily",
    }
    expected_cols = base_cols | feature_cols
    assert expected_cols == set(df.columns)
    assert {"sma_20", "std_20", "bb_mid_20_2", "macd_12_26_9"}.issubset(df.columns)

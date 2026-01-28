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
    }
    feature_cols = {
        "ema_20",
        "rsi_14",
        "atr_14",
        "sma_20",
        "std_20",
        "bb_mid_20_2",
        "bb_upper_20_2",
        "bb_lower_20_2",
        "macd_12_26_9",
        "macd_signal_12_26_9",
        "macd_hist_12_26_9",
    }
    expected_cols = base_cols | feature_cols
    assert expected_cols == set(df.columns)
    assert {"sma_20", "std_20", "bb_mid_20_2", "macd_12_26_9"}.issubset(df.columns)

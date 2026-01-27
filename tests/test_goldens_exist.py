"""Test that golden expected.csv exists and has required columns."""

import pandas as pd
from pathlib import Path


def test_goldens_exist() -> None:
    path = Path("tests/goldens/expected.csv")
    assert path.exists()

    df = pd.read_csv(path)
    assert len(df) >= 150

    expected_cols = {
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "rsi_14",
        "ema_20",
        "atr_14",
    }
    assert expected_cols.issubset(df.columns)

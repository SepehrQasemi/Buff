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

    assert ema.dropna().shape[0] > 0
    assert atr.dropna().shape[0] > 0
    assert (atr.dropna() >= 0).all()

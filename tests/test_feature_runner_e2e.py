"""End-to-end feature runner test against goldens."""

import numpy as np
import pandas as pd

from buff.features.runner import run_features


def test_feature_runner_e2e() -> None:
    df = pd.read_csv("tests/goldens/expected.csv")
    out = run_features(df)

    assert out.shape[0] == len(df)
    assert list(out.columns) == ["ema_20", "rsi_14", "atr_14"]

    expected = df.set_index(pd.to_datetime(df["timestamp"], utc=True))

    np.testing.assert_allclose(out["ema_20"].to_numpy(), expected["ema_20"].to_numpy(), rtol=1e-6, atol=1e-6, equal_nan=True)
    np.testing.assert_allclose(out["rsi_14"].to_numpy(), expected["rsi_14"].to_numpy(), rtol=1e-6, atol=1e-6, equal_nan=True)
    np.testing.assert_allclose(out["atr_14"].to_numpy(), expected["atr_14"].to_numpy(), rtol=1e-6, atol=1e-6, equal_nan=True)

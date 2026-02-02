from __future__ import annotations

import numpy as np
import pandas as pd

from features.build_features import build_features
from tests.fixtures.ohlcv_factory import make_ohlcv


def _perturb_future(df: pd.DataFrame, cutoff_ms: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    mutated = df.copy()
    mask = mutated["timestamp"] > cutoff_ms
    count = int(mask.sum())
    if count == 0:
        return mutated

    base = rng.normal(100.0, 5.0, size=count)
    open_ = base + rng.normal(0.0, 0.5, size=count)
    close = base + rng.normal(0.0, 0.5, size=count)
    high = np.maximum(open_, close) + rng.uniform(0.1, 1.5, size=count)
    low = np.minimum(open_, close) - rng.uniform(0.1, 1.5, size=count)
    volume = rng.uniform(500.0, 2000.0, size=count)

    mutated.loc[mask, "open"] = open_
    mutated.loc[mask, "high"] = high
    mutated.loc[mask, "low"] = low
    mutated.loc[mask, "close"] = close
    mutated.loc[mask, "volume"] = volume
    return mutated


def _assert_no_future_leakage(df: pd.DataFrame, cutoff_ms: int, seed: int) -> None:
    baseline = build_features(df)
    mutated = _perturb_future(df, cutoff_ms, seed)
    changed = build_features(mutated)

    cutoff_ts = pd.to_datetime(cutoff_ms, unit="ms", utc=True)
    pd.testing.assert_frame_equal(
        baseline.loc[:cutoff_ts],
        changed.loc[:cutoff_ts],
        check_exact=True,
    )


def test_no_leakage_future_perturbation() -> None:
    df = make_ohlcv(240)
    cutoff_mid = int(df["timestamp"].iloc[len(df) // 2])
    cutoff_near_end = int(df["timestamp"].iloc[-10])

    _assert_no_future_leakage(df, cutoff_mid, seed=123)
    _assert_no_future_leakage(df, cutoff_near_end, seed=456)

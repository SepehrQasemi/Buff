from __future__ import annotations

import numpy as np

from features.build_features import build_features
from features.regime import classify_regimes
from tests.fixtures.ohlcv_factory import make_ohlcv


def test_regime_stability() -> None:
    df = make_ohlcv(260)
    base_features = build_features(df)
    base = classify_regimes(base_features)

    rng = np.random.default_rng(42)
    noise = rng.normal(0.0, 0.001, size=len(df))

    noisy = df.copy()
    scale = 1.0 + noise
    noisy["open"] = noisy["open"] * scale
    noisy["high"] = noisy["high"] * scale
    noisy["low"] = noisy["low"] * scale
    noisy["close"] = noisy["close"] * scale

    noisy_features = build_features(noisy)
    noisy_regimes = classify_regimes(noisy_features)

    warmup = 60
    base_slice = base.iloc[warmup:]
    noisy_slice = noisy_regimes.iloc[warmup:]

    for col in ["trend_state", "momentum_state", "volatility_regime"]:
        match_ratio = (base_slice[col] == noisy_slice[col]).mean()
        assert match_ratio >= 0.7

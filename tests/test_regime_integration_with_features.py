"""Integration test using golden feature outputs."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from buff.regimes.evaluator import evaluate_regime
from buff.regimes.parser import load_regime_config


def test_regime_integration_with_features() -> None:
    df = pd.read_csv(Path("tests/goldens/expected.csv"))
    df["atr_pct"] = df["atr_14"] / df["close"]

    close = df["close"].astype(float)
    log_returns = np.log(close).diff()
    df["realized_vol_20"] = log_returns.rolling(window=20, min_periods=20).std(ddof=0)

    row = df.iloc[-1].to_dict()
    config = load_regime_config(Path("knowledge/regimes.yaml"))
    decision = evaluate_regime(row, config)
    assert decision.regime_id in {
        "RISK_OFF",
        "HIGH_VOL_TREND",
        "LOW_VOL_TREND",
        "HIGH_VOL_RANGE",
        "LOW_VOL_RANGE",
        "MEAN_REVERSION_BIAS",
        "NEUTRAL",
    }

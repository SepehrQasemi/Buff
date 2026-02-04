from __future__ import annotations

import pandas as pd
import pytest

from strategy_registry.builtins import register_builtin_strategies
from strategy_registry import get_strategy, run_strategy
from strategies.runners import trend_follow_v1


def test_missing_close_fails_closed() -> None:
    features_df = pd.DataFrame(
        {
            "ema_20": [1.0, 1.1],
            "ema_50": [1.0, 1.0],
            "rsi_14": [50.0, 60.0],
            "atr_14": [1.0, 1.0],
        }
    )
    metadata = {
        "bundle_fingerprint": "test-bundle",
        "instrument": "BTCUSDT",
        "features": [
            {"feature_id": "ema_20", "version": 1, "outputs": ["ema_20"]},
            {"feature_id": "ema_50", "version": 1, "outputs": ["ema_50"]},
            {"feature_id": "rsi_14", "version": 1, "outputs": ["rsi_14"]},
            {"feature_id": "atr_14", "version": 1, "outputs": ["atr_14"]},
        ],
    }

    register_builtin_strategies()
    strategy = get_strategy("TREND_FOLLOW_V1@1.0.0")
    with pytest.raises(ValueError, match="strategy_missing_column:close"):
        run_strategy(strategy, features_df, metadata, "2026-02-01T00:00:00Z")


def test_atr_guardrails_cap_position_size() -> None:
    features_df = pd.DataFrame(
        {
            "close": [100.0, 100.0],
            "ema_20": [99.0, 101.0],
            "ema_50": [100.0, 100.0],
            "rsi_14": [50.0, 60.0],
            "atr_14": [0.0, 0.0],
        }
    )
    metadata = {
        "bundle_fingerprint": "test-bundle",
        "instrument": "BTCUSDT",
        "features": [
            {"feature_id": "ema_20", "version": 1, "outputs": ["ema_20"]},
            {"feature_id": "ema_50", "version": 1, "outputs": ["ema_50"]},
            {"feature_id": "rsi_14", "version": 1, "outputs": ["rsi_14"]},
            {"feature_id": "atr_14", "version": 1, "outputs": ["atr_14"]},
        ],
    }

    register_builtin_strategies()
    strategy = get_strategy("TREND_FOLLOW_V1@1.0.0")
    decision = run_strategy(strategy, features_df, metadata, "2026-02-01T00:01:00Z")

    max_by_notional = trend_follow_v1.MAX_NOTIONAL / 100.0
    assert decision.risk.max_position_size == pytest.approx(max_by_notional, rel=1e-9)
    assert decision.risk.stop_loss < 100.0
    assert decision.risk.take_profit > 100.0

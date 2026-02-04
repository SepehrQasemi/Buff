from __future__ import annotations

import pandas as pd
import pytest

from buff.features.indicators import atr_wilder, bollinger_bands, rsi_wilder
from strategy_registry import get_strategy, run_strategy
from strategy_registry.builtins import register_builtin_strategies
from strategies.runners import mean_revert_v1
from tests.fixtures.ohlcv_factory import make_ohlcv


def _expected_action(frame: pd.DataFrame) -> str:
    latest = frame.dropna().iloc[-1]
    entry = (
        latest["close"] < latest["bb_lower_20_2"] and latest["rsi_14"] < mean_revert_v1.RSI_ENTRY
    )
    exit_ = latest["close"] >= latest["bb_mid_20_2"] or latest["rsi_14"] > mean_revert_v1.RSI_EXIT
    if entry:
        return "ENTER_LONG"
    if exit_:
        return "EXIT_LONG"
    return "HOLD"


def test_mean_revert_v1_end_to_end_decision() -> None:
    df = make_ohlcv(120)
    close = pd.to_numeric(df["close"], errors="coerce")
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")

    bb = bollinger_bands(close, period=20, k=2.0, ddof=0)
    features_df = pd.DataFrame(
        {
            "close": close,
            "bb_mid_20_2": bb["mid"],
            "bb_upper_20_2": bb["upper"],
            "bb_lower_20_2": bb["lower"],
            "rsi_14": rsi_wilder(close, period=14),
            "atr_14": atr_wilder(high, low, close, period=14),
        }
    )
    features_df.attrs["instrument"] = "BTCUSDT"

    last_ts = pd.to_datetime(df["timestamp"].iloc[-1], unit="ms", utc=True)
    as_of_utc = last_ts.isoformat().replace("+00:00", "Z")
    metadata = {
        "bundle_fingerprint": "test-bundle",
        "instrument": "BTCUSDT",
        "features": [
            {
                "feature_id": "bbands_20_2",
                "version": 1,
                "outputs": ["bb_mid_20_2", "bb_upper_20_2", "bb_lower_20_2"],
            },
            {"feature_id": "rsi_14", "version": 1, "outputs": ["rsi_14"]},
            {"feature_id": "atr_14", "version": 1, "outputs": ["atr_14"]},
        ],
    }

    register_builtin_strategies()
    strategy = get_strategy("MEAN_REVERT_V1@1.0.0")
    decision = run_strategy(strategy, features_df, metadata, as_of_utc)

    expected_action = _expected_action(features_df)
    assert decision.action.value == expected_action

    latest = features_df[["close", "atr_14"]].dropna().iloc[-1]
    entry_price = float(latest["close"])
    atr = float(latest["atr_14"])
    atr_eff = max(atr, mean_revert_v1.ATR_EPS)

    stop_loss = entry_price - (mean_revert_v1.ATR_STOP_MULT * atr_eff)
    take_profit = entry_price + (mean_revert_v1.ATR_TAKE_MULT * atr_eff)
    position_size = (mean_revert_v1.DEFAULT_EQUITY * mean_revert_v1.RISK_PCT) / (
        mean_revert_v1.ATR_STOP_MULT * atr_eff
    )
    max_by_notional = mean_revert_v1.MAX_NOTIONAL / entry_price
    position_size = min(position_size, max_by_notional, mean_revert_v1.MAX_POSITION_SIZE)

    assert decision.risk.stop_loss == pytest.approx(stop_loss, rel=1e-9)
    assert decision.risk.take_profit == pytest.approx(take_profit, rel=1e-9)
    assert decision.risk.max_position_size == pytest.approx(position_size, rel=1e-9)

    rationale = " ".join(decision.rationale)
    assert "indicators=" in rationale
    assert "thresholds=" in rationale

    decision_b = run_strategy(strategy, features_df, metadata, as_of_utc)
    assert decision.to_dict() == decision_b.to_dict()


def test_mean_revert_v1_respects_as_of_utc() -> None:
    timestamps = pd.to_datetime(
        ["2026-02-01T00:00:00Z", "2026-02-01T00:01:00Z", "2026-02-01T00:02:00Z"],
        utc=True,
    )
    features_df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "close": [100.0, 100.0, 95.0],
            "bb_mid_20_2": [101.0, 101.0, 101.0],
            "bb_upper_20_2": [102.0, 102.0, 102.0],
            "bb_lower_20_2": [99.0, 99.0, 99.0],
            "rsi_14": [40.0, 40.0, 30.0],
            "atr_14": [1.0, 1.0, 1.0],
        }
    )
    metadata = {
        "bundle_fingerprint": "test-bundle",
        "instrument": "BTCUSDT",
        "features": [
            {
                "feature_id": "bbands_20_2",
                "version": 1,
                "outputs": ["bb_mid_20_2", "bb_upper_20_2", "bb_lower_20_2"],
            },
            {"feature_id": "rsi_14", "version": 1, "outputs": ["rsi_14"]},
            {"feature_id": "atr_14", "version": 1, "outputs": ["atr_14"]},
        ],
    }

    register_builtin_strategies()
    strategy = get_strategy("MEAN_REVERT_V1@1.0.0")
    decision = run_strategy(strategy, features_df, metadata, "2026-02-01T00:01:00Z")
    assert decision.action.value == "HOLD"

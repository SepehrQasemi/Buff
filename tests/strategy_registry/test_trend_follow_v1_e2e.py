from __future__ import annotations

import pandas as pd
import pytest

from buff.features.indicators import atr_wilder, ema, rsi_wilder
from strategy_registry import get_strategy, run_strategy
from strategy_registry.builtins import register_builtin_strategies
from strategies.runners import trend_follow_v1
from tests.fixtures.ohlcv_factory import make_ohlcv


def _expected_action(frame: pd.DataFrame) -> str:
    latest = frame.dropna().iloc[-2:]
    prev = latest.iloc[0]
    curr = latest.iloc[1]
    cross_up = prev["ema_20"] <= prev["ema_50"] and curr["ema_20"] > curr["ema_50"]
    cross_down = prev["ema_20"] >= prev["ema_50"] and curr["ema_20"] < curr["ema_50"]
    rsi_entry = curr["rsi_14"] > trend_follow_v1.RSI_ENTRY
    rsi_exit = curr["rsi_14"] < trend_follow_v1.RSI_EXIT
    if cross_up and rsi_entry:
        return "ENTER_LONG"
    if cross_down or rsi_exit:
        return "EXIT_LONG"
    return "HOLD"


def test_trend_follow_v1_end_to_end_decision() -> None:
    df = make_ohlcv(120)
    close = pd.to_numeric(df["close"], errors="coerce")
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")

    features_df = pd.DataFrame(
        {
            "close": close,
            "ema_20": ema(close, period=20),
            "ema_50": ema(close, period=50),
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
            {"feature_id": "ema_20", "version": 1, "outputs": ["ema_20"]},
            {"feature_id": "ema_50", "version": 1, "outputs": ["ema_50"]},
            {"feature_id": "rsi_14", "version": 1, "outputs": ["rsi_14"]},
            {"feature_id": "atr_14", "version": 1, "outputs": ["atr_14"]},
        ],
    }

    register_builtin_strategies()
    strategy = get_strategy("TREND_FOLLOW_V1@1.0.0")
    decision = run_strategy(strategy, features_df, metadata, as_of_utc)

    expected_action = _expected_action(features_df[["close", "ema_20", "ema_50", "rsi_14", "atr_14"]])
    assert decision.action.value == expected_action

    latest = features_df[["close", "atr_14"]].dropna().iloc[-1]
    entry_price = float(latest["close"])
    atr = float(latest["atr_14"])

    stop_loss = entry_price - (trend_follow_v1.ATR_STOP_MULT * atr)
    take_profit = entry_price + (trend_follow_v1.ATR_TAKE_MULT * atr)
    position_size = (trend_follow_v1.DEFAULT_EQUITY * trend_follow_v1.RISK_PCT) / (
        trend_follow_v1.ATR_STOP_MULT * atr
    )

    assert decision.risk.stop_loss == pytest.approx(stop_loss, rel=1e-9)
    assert decision.risk.take_profit == pytest.approx(take_profit, rel=1e-9)
    assert decision.risk.max_position_size == pytest.approx(position_size, rel=1e-9)

    rationale = " ".join(decision.rationale)
    assert "indicators=" in rationale
    assert "thresholds=" in rationale

    decision_b = run_strategy(strategy, features_df, metadata, as_of_utc)
    assert decision.to_dict() == decision_b.to_dict()


def test_trend_follow_v1_respects_as_of_utc() -> None:
    timestamps = pd.to_datetime(
        ["2026-02-01T00:00:00Z", "2026-02-01T00:01:00Z", "2026-02-01T00:02:00Z"],
        utc=True,
    )
    features_df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "close": [100.0, 100.0, 100.0],
            "ema_20": [99.0, 99.5, 101.0],
            "ema_50": [100.0, 100.0, 100.0],
            "rsi_14": [50.0, 50.0, 60.0],
            "atr_14": [1.0, 1.0, 1.0],
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
    assert decision.action.value == "HOLD"

from __future__ import annotations

import copy
from typing import Any

from strategies.builtins.common import (
    BuiltinStrategyDefinition,
    intent_response,
    last_two,
    last_value,
    macd,
    numeric_series,
    prepare_context,
    roc,
    stochastic_kd,
    strategy_schema,
)


_MACD_SCHEMA = strategy_schema(
    strategy_id="macd_momentum",
    name="MACD Momentum",
    version="1.0.0",
    category="momentum",
    description="MACD line momentum cross.",
    warmup_bars=35,
    params=[
        {
            "name": "fast",
            "type": "int",
            "min": 5,
            "max": 20,
            "default": 12,
            "step": 1,
            "description": "MACD fast EMA.",
        },
        {
            "name": "slow",
            "type": "int",
            "min": 10,
            "max": 50,
            "default": 26,
            "step": 1,
            "description": "MACD slow EMA.",
        },
        {
            "name": "signal",
            "type": "int",
            "min": 3,
            "max": 20,
            "default": 9,
            "step": 1,
            "description": "Signal EMA.",
        },
        {
            "name": "hist_threshold",
            "type": "float",
            "min": 0.0,
            "max": 1.0,
            "default": 0.0,
            "step": 0.01,
            "description": "Histogram threshold for entries.",
        },
    ],
    inputs={"series": ["open", "high", "low", "close", "volume"]},
    tags=["momentum", "macd"],
)


def macd_momentum_get_schema() -> dict[str, Any]:
    return copy.deepcopy(_MACD_SCHEMA)


def macd_momentum_on_bar(ctx) -> dict[str, Any]:
    history, params, in_warmup, _ = prepare_context(ctx, _MACD_SCHEMA)
    fast = int(params["fast"])
    slow = int(params["slow"])
    signal = int(params["signal"])
    hist_threshold = float(params["hist_threshold"])
    if fast >= slow:
        raise ValueError("strategy_params_invalid")
    warmup = max(slow + signal - 1, _MACD_SCHEMA["warmup_bars"])
    if len(history) < warmup or in_warmup:
        return intent_response("HOLD", tags=["warmup"])

    close = numeric_series(history, "close")
    macd_df = macd(close, fast=fast, slow=slow, signal=signal)
    pair_macd = last_two(macd_df["macd"])
    pair_signal = last_two(macd_df["signal"])
    hist = last_value(macd_df["hist"])
    if pair_macd is None or pair_signal is None or hist is None:
        return intent_response("HOLD", tags=["insufficient_history"])

    prev_macd, curr_macd = pair_macd
    prev_signal, curr_signal = pair_signal
    cross_up = prev_macd <= prev_signal and curr_macd > curr_signal and hist > hist_threshold
    cross_down = prev_macd >= prev_signal and curr_macd < curr_signal and hist < -hist_threshold

    if cross_up:
        return intent_response("ENTER_LONG", confidence=0.65, tags=["macd_cross_up"])
    if cross_down:
        return intent_response("ENTER_SHORT", confidence=0.65, tags=["macd_cross_down"])
    if curr_macd < curr_signal:
        return intent_response("EXIT_LONG", confidence=0.4, tags=["macd_exit_long"])
    if curr_macd > curr_signal:
        return intent_response("EXIT_SHORT", confidence=0.4, tags=["macd_exit_short"])
    return intent_response("HOLD")


MACD_MOMENTUM = BuiltinStrategyDefinition(
    strategy_id=_MACD_SCHEMA["id"],
    version=_MACD_SCHEMA["version"],
    get_schema=macd_momentum_get_schema,
    on_bar=macd_momentum_on_bar,
)


_ROC_SCHEMA = strategy_schema(
    strategy_id="roc_momentum",
    name="ROC Momentum",
    version="1.0.0",
    category="momentum",
    description="Rate-of-change momentum bursts.",
    warmup_bars=12,
    params=[
        {
            "name": "period",
            "type": "int",
            "min": 5,
            "max": 50,
            "default": 12,
            "step": 1,
            "description": "ROC lookback.",
        },
        {
            "name": "entry_threshold",
            "type": "float",
            "min": 0.2,
            "max": 5.0,
            "default": 1.0,
            "step": 0.1,
            "description": "Entry threshold (percent).",
        },
        {
            "name": "exit_threshold",
            "type": "float",
            "min": -1.0,
            "max": 1.0,
            "default": 0.0,
            "step": 0.1,
            "description": "Exit threshold toward zero.",
        },
    ],
    inputs={"series": ["open", "high", "low", "close", "volume"]},
    tags=["momentum", "roc"],
)


def roc_momentum_get_schema() -> dict[str, Any]:
    return copy.deepcopy(_ROC_SCHEMA)


def roc_momentum_on_bar(ctx) -> dict[str, Any]:
    history, params, in_warmup, _ = prepare_context(ctx, _ROC_SCHEMA)
    period = int(params["period"])
    entry_th = float(params["entry_threshold"])
    exit_th = float(params["exit_threshold"])
    warmup = max(period, _ROC_SCHEMA["warmup_bars"])
    if len(history) < warmup or in_warmup:
        return intent_response("HOLD", tags=["warmup"])

    close = numeric_series(history, "close")
    roc_series = roc(close, period=period)
    value = last_value(roc_series)
    if value is None:
        return intent_response("HOLD", tags=["insufficient_history"])

    if value >= entry_th:
        return intent_response("ENTER_LONG", confidence=0.6, tags=["roc_up"])
    if value <= -entry_th:
        return intent_response("ENTER_SHORT", confidence=0.6, tags=["roc_down"])
    if value <= exit_th:
        return intent_response("EXIT_LONG", confidence=0.4, tags=["roc_exit_long"])
    if value >= -exit_th:
        return intent_response("EXIT_SHORT", confidence=0.4, tags=["roc_exit_short"])
    return intent_response("HOLD")


ROC_MOMENTUM = BuiltinStrategyDefinition(
    strategy_id=_ROC_SCHEMA["id"],
    version=_ROC_SCHEMA["version"],
    get_schema=roc_momentum_get_schema,
    on_bar=roc_momentum_on_bar,
)


_STOCH_SCHEMA = strategy_schema(
    strategy_id="stochastic_momentum",
    name="Stochastic Momentum",
    version="1.0.0",
    category="momentum",
    description="Stochastic momentum cross above/below thresholds.",
    warmup_bars=20,
    params=[
        {
            "name": "k_period",
            "type": "int",
            "min": 5,
            "max": 50,
            "default": 14,
            "step": 1,
            "description": "Stochastic %K lookback.",
        },
        {
            "name": "d_period",
            "type": "int",
            "min": 2,
            "max": 10,
            "default": 3,
            "step": 1,
            "description": "Stochastic %D smoothing.",
        },
        {
            "name": "smooth_k",
            "type": "int",
            "min": 1,
            "max": 10,
            "default": 3,
            "step": 1,
            "description": "%K smoothing.",
        },
        {
            "name": "entry_threshold",
            "type": "float",
            "min": 50.0,
            "max": 90.0,
            "default": 60.0,
            "step": 1.0,
            "description": "Momentum threshold for entries.",
        },
        {
            "name": "exit_threshold",
            "type": "float",
            "min": 10.0,
            "max": 60.0,
            "default": 50.0,
            "step": 1.0,
            "description": "Exit threshold toward neutral.",
        },
    ],
    inputs={"series": ["open", "high", "low", "close", "volume"]},
    tags=["momentum", "stochastic"],
)


def stochastic_momentum_get_schema() -> dict[str, Any]:
    return copy.deepcopy(_STOCH_SCHEMA)


def stochastic_momentum_on_bar(ctx) -> dict[str, Any]:
    history, params, in_warmup, _ = prepare_context(ctx, _STOCH_SCHEMA)
    k_period = int(params["k_period"])
    d_period = int(params["d_period"])
    smooth_k = int(params["smooth_k"])
    entry_th = float(params["entry_threshold"])
    exit_th = float(params["exit_threshold"])
    if exit_th >= entry_th:
        raise ValueError("strategy_params_invalid")

    warmup = max(k_period + smooth_k + d_period, _STOCH_SCHEMA["warmup_bars"])
    if len(history) < warmup or in_warmup:
        return intent_response("HOLD", tags=["warmup"])

    high = numeric_series(history, "high")
    low = numeric_series(history, "low")
    close = numeric_series(history, "close")

    stoch = stochastic_kd(
        high,
        low,
        close,
        k_period=k_period,
        d_period=d_period,
        smooth_k=smooth_k,
    )
    pair_k = last_two(stoch["k"])
    pair_d = last_two(stoch["d"])
    if pair_k is None or pair_d is None:
        return intent_response("HOLD", tags=["insufficient_history"])

    prev_k, curr_k = pair_k
    prev_d, curr_d = pair_d

    cross_up = prev_k <= prev_d and curr_k > curr_d
    cross_down = prev_k >= prev_d and curr_k < curr_d
    short_threshold = 100.0 - entry_th
    short_exit = 100.0 - exit_th

    if cross_up and curr_k >= entry_th:
        return intent_response("ENTER_LONG", confidence=0.6, tags=["stoch_momentum_up"])
    if cross_down and curr_k <= short_threshold:
        return intent_response("ENTER_SHORT", confidence=0.6, tags=["stoch_momentum_down"])
    if curr_k <= exit_th:
        return intent_response("EXIT_LONG", confidence=0.4, tags=["stoch_exit_long"])
    if curr_k >= short_exit:
        return intent_response("EXIT_SHORT", confidence=0.4, tags=["stoch_exit_short"])
    return intent_response("HOLD")


STOCHASTIC_MOMENTUM = BuiltinStrategyDefinition(
    strategy_id=_STOCH_SCHEMA["id"],
    version=_STOCH_SCHEMA["version"],
    get_schema=stochastic_momentum_get_schema,
    on_bar=stochastic_momentum_on_bar,
)


__all__ = ["MACD_MOMENTUM", "ROC_MOMENTUM", "STOCHASTIC_MOMENTUM"]

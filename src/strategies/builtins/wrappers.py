from __future__ import annotations

import copy
from typing import Any

from strategies.builtins.common import (
    BuiltinStrategyDefinition,
    intent_response,
    numeric_series,
    prepare_context,
    strategy_schema,
)


_TIME_EXIT_SCHEMA = strategy_schema(
    strategy_id="time_based_exit_wrapper",
    name="Time-based Exit Wrapper",
    version="1.0.0",
    category="wrapper",
    description="Exit after a fixed number of bars in trade.",
    warmup_bars=1,
    params=[
        {
            "name": "max_bars",
            "type": "int",
            "min": 1,
            "max": 200,
            "default": 10,
            "step": 1,
            "description": "Maximum bars to hold a trade.",
        }
    ],
    inputs={"series": ["open", "high", "low", "close", "volume"]},
    tags=["wrapper", "time_exit"],
)


def time_based_exit_wrapper_get_schema() -> dict[str, Any]:
    return copy.deepcopy(_TIME_EXIT_SCHEMA)


def time_based_exit_wrapper_on_bar(ctx) -> dict[str, Any]:
    history, params, in_warmup, position = prepare_context(ctx, _TIME_EXIT_SCHEMA)
    max_bars = int(params["max_bars"])
    if max_bars <= 0:
        raise ValueError("strategy_params_invalid")
    if len(history) < _TIME_EXIT_SCHEMA["warmup_bars"] or in_warmup:
        return intent_response("HOLD", tags=["warmup"])
    if position is None:
        return intent_response("HOLD", tags=["no_position"])
    if position.bars_in_trade >= max_bars:
        if position.side == "LONG":
            return intent_response("EXIT_LONG", confidence=0.6, tags=["time_exit_long"])
        return intent_response("EXIT_SHORT", confidence=0.6, tags=["time_exit_short"])
    return intent_response("HOLD")


TIME_BASED_EXIT_WRAPPER = BuiltinStrategyDefinition(
    strategy_id=_TIME_EXIT_SCHEMA["id"],
    version=_TIME_EXIT_SCHEMA["version"],
    get_schema=time_based_exit_wrapper_get_schema,
    on_bar=time_based_exit_wrapper_on_bar,
)


_TRAIL_SCHEMA = strategy_schema(
    strategy_id="trailing_stop_wrapper",
    name="Trailing Stop Wrapper",
    version="1.0.0",
    category="wrapper",
    description="Exit on trailing stop from max/min favorable price.",
    warmup_bars=1,
    params=[
        {
            "name": "trail_pct",
            "type": "float",
            "min": 0.001,
            "max": 0.2,
            "default": 0.02,
            "step": 0.001,
            "description": "Trailing stop percent.",
        }
    ],
    inputs={"series": ["open", "high", "low", "close", "volume"]},
    tags=["wrapper", "trailing_stop"],
)


def trailing_stop_wrapper_get_schema() -> dict[str, Any]:
    return copy.deepcopy(_TRAIL_SCHEMA)


def trailing_stop_wrapper_on_bar(ctx) -> dict[str, Any]:
    history, params, in_warmup, position = prepare_context(ctx, _TRAIL_SCHEMA)
    trail_pct = float(params["trail_pct"])
    if trail_pct <= 0.0:
        raise ValueError("strategy_params_invalid")
    if len(history) < _TRAIL_SCHEMA["warmup_bars"] or in_warmup:
        return intent_response("HOLD", tags=["warmup"])
    if position is None:
        return intent_response("HOLD", tags=["no_position"])

    high = numeric_series(history, "high")
    low = numeric_series(history, "low")
    curr_high = float(high.iloc[-1])
    curr_low = float(low.iloc[-1])

    if position.side == "LONG":
        trailing = position.max_price * (1.0 - trail_pct)
        if curr_low <= trailing:
            return intent_response("EXIT_LONG", confidence=0.6, tags=["trailing_stop_long"])
    else:
        trailing = position.min_price * (1.0 + trail_pct)
        if curr_high >= trailing:
            return intent_response("EXIT_SHORT", confidence=0.6, tags=["trailing_stop_short"])
    return intent_response("HOLD")


TRAILING_STOP_WRAPPER = BuiltinStrategyDefinition(
    strategy_id=_TRAIL_SCHEMA["id"],
    version=_TRAIL_SCHEMA["version"],
    get_schema=trailing_stop_wrapper_get_schema,
    on_bar=trailing_stop_wrapper_on_bar,
)


_RR_SCHEMA = strategy_schema(
    strategy_id="fixed_rr_stop_target_wrapper",
    name="Fixed RR Stop/Target Wrapper",
    version="1.0.0",
    category="wrapper",
    description="Exit when fixed stop or target is hit.",
    warmup_bars=1,
    params=[
        {
            "name": "stop_pct",
            "type": "float",
            "min": 0.001,
            "max": 0.1,
            "default": 0.01,
            "step": 0.001,
            "description": "Stop distance percent.",
        },
        {
            "name": "reward_ratio",
            "type": "float",
            "min": 0.5,
            "max": 5.0,
            "default": 2.0,
            "step": 0.1,
            "description": "Reward-to-risk ratio.",
        },
    ],
    inputs={"series": ["open", "high", "low", "close", "volume"]},
    tags=["wrapper", "risk"],
)


def fixed_rr_stop_target_wrapper_get_schema() -> dict[str, Any]:
    return copy.deepcopy(_RR_SCHEMA)


def fixed_rr_stop_target_wrapper_on_bar(ctx) -> dict[str, Any]:
    history, params, in_warmup, position = prepare_context(ctx, _RR_SCHEMA)
    stop_pct = float(params["stop_pct"])
    reward_ratio = float(params["reward_ratio"])
    if stop_pct <= 0.0 or reward_ratio <= 0.0:
        raise ValueError("strategy_params_invalid")
    if len(history) < _RR_SCHEMA["warmup_bars"] or in_warmup:
        return intent_response("HOLD", tags=["warmup"])
    if position is None:
        return intent_response("HOLD", tags=["no_position"])

    high = numeric_series(history, "high")
    low = numeric_series(history, "low")
    curr_high = float(high.iloc[-1])
    curr_low = float(low.iloc[-1])
    entry = float(position.entry_price)

    if position.side == "LONG":
        stop = entry * (1.0 - stop_pct)
        target = entry * (1.0 + stop_pct * reward_ratio)
        if curr_low <= stop:
            return intent_response("EXIT_LONG", confidence=0.65, tags=["fixed_rr_stop_long"])
        if curr_high >= target:
            return intent_response("EXIT_LONG", confidence=0.65, tags=["fixed_rr_target_long"])
    else:
        stop = entry * (1.0 + stop_pct)
        target = entry * (1.0 - stop_pct * reward_ratio)
        if curr_high >= stop:
            return intent_response("EXIT_SHORT", confidence=0.65, tags=["fixed_rr_stop_short"])
        if curr_low <= target:
            return intent_response("EXIT_SHORT", confidence=0.65, tags=["fixed_rr_target_short"])
    return intent_response("HOLD")


FIXED_RR_STOP_TARGET_WRAPPER = BuiltinStrategyDefinition(
    strategy_id=_RR_SCHEMA["id"],
    version=_RR_SCHEMA["version"],
    get_schema=fixed_rr_stop_target_wrapper_get_schema,
    on_bar=fixed_rr_stop_target_wrapper_on_bar,
)


__all__ = [
    "FIXED_RR_STOP_TARGET_WRAPPER",
    "TIME_BASED_EXIT_WRAPPER",
    "TRAILING_STOP_WRAPPER",
]

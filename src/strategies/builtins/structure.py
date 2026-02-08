from __future__ import annotations

import copy
from typing import Any

from strategies.builtins.common import (
    BuiltinStrategyDefinition,
    intent_response,
    last_pivot_levels,
    numeric_series,
    prepare_context,
    rolling_max,
    rolling_min,
    strategy_schema,
)


_PIVOT_SCHEMA = strategy_schema(
    strategy_id="pivot_breakout",
    name="Pivot Breakout",
    version="1.0.0",
    category="structure",
    description="Breakout above/below confirmed pivot levels.",
    warmup_bars=7,
    params=[
        {
            "name": "pivot_lookback",
            "type": "int",
            "min": 2,
            "max": 10,
            "default": 3,
            "step": 1,
            "description": "Bars on each side to confirm pivots.",
        },
        {
            "name": "buffer_pct",
            "type": "float",
            "min": 0.0,
            "max": 0.02,
            "default": 0.0,
            "step": 0.001,
            "description": "Breakout buffer percent.",
        },
    ],
    inputs={"series": ["open", "high", "low", "close", "volume"]},
    tags=["structure", "pivot"],
)


def pivot_breakout_get_schema() -> dict[str, Any]:
    return copy.deepcopy(_PIVOT_SCHEMA)


def pivot_breakout_on_bar(ctx) -> dict[str, Any]:
    history, params, in_warmup, _ = prepare_context(ctx, _PIVOT_SCHEMA)
    lookback = int(params["pivot_lookback"])
    buffer_pct = float(params["buffer_pct"])
    warmup = max(lookback * 2 + 1, _PIVOT_SCHEMA["warmup_bars"])
    if len(history) < warmup or in_warmup:
        return intent_response("HOLD", tags=["warmup"])

    high = numeric_series(history, "high")
    low = numeric_series(history, "low")
    close = numeric_series(history, "close")

    pivot_high, pivot_low = last_pivot_levels(high, low, lookback)
    if pivot_high is None and pivot_low is None:
        return intent_response("HOLD", tags=["no_pivot"])

    price = float(close.iloc[-1])
    if pivot_high is not None and price > pivot_high * (1.0 + buffer_pct):
        return intent_response("ENTER_LONG", confidence=0.65, tags=["pivot_breakout_up"])
    if pivot_low is not None and price < pivot_low * (1.0 - buffer_pct):
        return intent_response("ENTER_SHORT", confidence=0.65, tags=["pivot_breakout_down"])
    if pivot_high is not None and price < pivot_high * (1.0 - buffer_pct):
        return intent_response("EXIT_LONG", confidence=0.4, tags=["pivot_exit_long"])
    if pivot_low is not None and price > pivot_low * (1.0 + buffer_pct):
        return intent_response("EXIT_SHORT", confidence=0.4, tags=["pivot_exit_short"])
    return intent_response("HOLD")


PIVOT_BREAKOUT = BuiltinStrategyDefinition(
    strategy_id=_PIVOT_SCHEMA["id"],
    version=_PIVOT_SCHEMA["version"],
    get_schema=pivot_breakout_get_schema,
    on_bar=pivot_breakout_on_bar,
)


_SR_SCHEMA = strategy_schema(
    strategy_id="sr_retest_rule_based",
    name="Support/Resistance Retest",
    version="1.0.0",
    category="structure",
    description="Breakout then retest of support/resistance levels.",
    warmup_bars=21,
    params=[
        {
            "name": "lookback",
            "type": "int",
            "min": 10,
            "max": 60,
            "default": 20,
            "step": 1,
            "description": "Support/resistance lookback.",
        },
        {
            "name": "breakout_buffer",
            "type": "float",
            "min": 0.0,
            "max": 0.02,
            "default": 0.002,
            "step": 0.001,
            "description": "Breakout buffer percent.",
        },
        {
            "name": "retest_tolerance",
            "type": "float",
            "min": 0.0,
            "max": 0.02,
            "default": 0.002,
            "step": 0.001,
            "description": "Retest tolerance percent.",
        },
    ],
    inputs={"series": ["open", "high", "low", "close", "volume"]},
    tags=["structure", "retest"],
)


def sr_retest_rule_based_get_schema() -> dict[str, Any]:
    return copy.deepcopy(_SR_SCHEMA)


def sr_retest_rule_based_on_bar(ctx) -> dict[str, Any]:
    history, params, in_warmup, _ = prepare_context(ctx, _SR_SCHEMA)
    lookback = int(params["lookback"])
    breakout_buffer = float(params["breakout_buffer"])
    retest_tolerance = float(params["retest_tolerance"])
    warmup = max(lookback + 1, _SR_SCHEMA["warmup_bars"])
    if len(history) < warmup or in_warmup:
        return intent_response("HOLD", tags=["warmup"])

    high = numeric_series(history, "high")
    low = numeric_series(history, "low")
    close = numeric_series(history, "close")

    resistance = rolling_max(high, lookback).shift(1)
    support = rolling_min(low, lookback).shift(1)
    if resistance.isna().iloc[-1] or support.isna().iloc[-1]:
        return intent_response("HOLD", tags=["insufficient_history"])

    prev_close = float(close.iloc[-2])
    curr_close = float(close.iloc[-1])
    curr_low = float(low.iloc[-1])
    curr_high = float(high.iloc[-1])
    res_level = float(resistance.iloc[-1])
    sup_level = float(support.iloc[-1])

    broke_up = prev_close > res_level * (1.0 + breakout_buffer)
    retest_up = curr_low <= res_level * (1.0 + retest_tolerance) and curr_close >= res_level

    broke_down = prev_close < sup_level * (1.0 - breakout_buffer)
    retest_down = curr_high >= sup_level * (1.0 - retest_tolerance) and curr_close <= sup_level

    if broke_up and retest_up:
        return intent_response("ENTER_LONG", confidence=0.65, tags=["sr_retest_long"])
    if broke_down and retest_down:
        return intent_response("ENTER_SHORT", confidence=0.65, tags=["sr_retest_short"])
    if curr_close < res_level:
        return intent_response("EXIT_LONG", confidence=0.4, tags=["sr_exit_long"])
    if curr_close > sup_level:
        return intent_response("EXIT_SHORT", confidence=0.4, tags=["sr_exit_short"])
    return intent_response("HOLD")


SR_RETEST_RULE_BASED = BuiltinStrategyDefinition(
    strategy_id=_SR_SCHEMA["id"],
    version=_SR_SCHEMA["version"],
    get_schema=sr_retest_rule_based_get_schema,
    on_bar=sr_retest_rule_based_on_bar,
)


__all__ = ["PIVOT_BREAKOUT", "SR_RETEST_RULE_BASED"]

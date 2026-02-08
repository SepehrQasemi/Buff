from __future__ import annotations

import copy
from typing import Any

from strategies.builtins.common import (
    BuiltinStrategyDefinition,
    adx_wilder,
    bollinger_bands,
    ema,
    intent_response,
    last_two,
    numeric_series,
    prepare_context,
    sma,
    strategy_schema,
    supertrend,
)


_SMA_SCHEMA = strategy_schema(
    strategy_id="sma_crossover",
    name="SMA Crossover",
    version="1.0.0",
    category="trend",
    description="Fast/slow SMA crossover trend-following.",
    warmup_bars=30,
    params=[
        {
            "name": "fast_period",
            "type": "int",
            "min": 2,
            "max": 50,
            "default": 10,
            "step": 1,
            "description": "Fast SMA lookback.",
        },
        {
            "name": "slow_period",
            "type": "int",
            "min": 5,
            "max": 200,
            "default": 30,
            "step": 1,
            "description": "Slow SMA lookback.",
        },
    ],
    inputs={"series": ["open", "high", "low", "close", "volume"]},
    tags=["trend", "crossover"],
)


def sma_crossover_get_schema() -> dict[str, Any]:
    return copy.deepcopy(_SMA_SCHEMA)


def sma_crossover_on_bar(ctx) -> dict[str, Any]:
    history, params, in_warmup, _ = prepare_context(ctx, _SMA_SCHEMA)
    fast = int(params["fast_period"])
    slow = int(params["slow_period"])
    if fast >= slow:
        raise ValueError("strategy_params_invalid")
    warmup = max(slow, _SMA_SCHEMA["warmup_bars"])
    if len(history) < warmup or in_warmup:
        return intent_response("HOLD", tags=["warmup"])

    close = numeric_series(history, "close")
    fast_series = sma(close, period=fast)
    slow_series = sma(close, period=slow)
    pair_fast = last_two(fast_series)
    pair_slow = last_two(slow_series)
    if pair_fast is None or pair_slow is None:
        return intent_response("HOLD", tags=["insufficient_history"])

    prev_fast, curr_fast = pair_fast
    prev_slow, curr_slow = pair_slow
    cross_up = prev_fast <= prev_slow and curr_fast > curr_slow
    cross_down = prev_fast >= prev_slow and curr_fast < curr_slow

    if cross_up:
        return intent_response("ENTER_LONG", confidence=0.6, tags=["sma_cross_up"])
    if cross_down:
        return intent_response("ENTER_SHORT", confidence=0.6, tags=["sma_cross_down"])
    return intent_response("HOLD")


SMA_CROSSOVER = BuiltinStrategyDefinition(
    strategy_id=_SMA_SCHEMA["id"],
    version=_SMA_SCHEMA["version"],
    get_schema=sma_crossover_get_schema,
    on_bar=sma_crossover_on_bar,
)


_EMA_SCHEMA = strategy_schema(
    strategy_id="ema_crossover",
    name="EMA Crossover",
    version="1.0.0",
    category="trend",
    description="Fast/slow EMA crossover trend-following.",
    warmup_bars=30,
    params=[
        {
            "name": "fast_period",
            "type": "int",
            "min": 2,
            "max": 50,
            "default": 12,
            "step": 1,
            "description": "Fast EMA lookback.",
        },
        {
            "name": "slow_period",
            "type": "int",
            "min": 5,
            "max": 200,
            "default": 26,
            "step": 1,
            "description": "Slow EMA lookback.",
        },
    ],
    inputs={"series": ["open", "high", "low", "close", "volume"]},
    tags=["trend", "crossover"],
)


def ema_crossover_get_schema() -> dict[str, Any]:
    return copy.deepcopy(_EMA_SCHEMA)


def ema_crossover_on_bar(ctx) -> dict[str, Any]:
    history, params, in_warmup, _ = prepare_context(ctx, _EMA_SCHEMA)
    fast = int(params["fast_period"])
    slow = int(params["slow_period"])
    if fast >= slow:
        raise ValueError("strategy_params_invalid")
    warmup = max(slow, _EMA_SCHEMA["warmup_bars"])
    if len(history) < warmup or in_warmup:
        return intent_response("HOLD", tags=["warmup"])

    close = numeric_series(history, "close")
    fast_series = ema(close, period=fast)
    slow_series = ema(close, period=slow)
    pair_fast = last_two(fast_series)
    pair_slow = last_two(slow_series)
    if pair_fast is None or pair_slow is None:
        return intent_response("HOLD", tags=["insufficient_history"])

    prev_fast, curr_fast = pair_fast
    prev_slow, curr_slow = pair_slow
    cross_up = prev_fast <= prev_slow and curr_fast > curr_slow
    cross_down = prev_fast >= prev_slow and curr_fast < curr_slow

    if cross_up:
        return intent_response("ENTER_LONG", confidence=0.6, tags=["ema_cross_up"])
    if cross_down:
        return intent_response("ENTER_SHORT", confidence=0.6, tags=["ema_cross_down"])
    return intent_response("HOLD")


EMA_CROSSOVER = BuiltinStrategyDefinition(
    strategy_id=_EMA_SCHEMA["id"],
    version=_EMA_SCHEMA["version"],
    get_schema=ema_crossover_get_schema,
    on_bar=ema_crossover_on_bar,
)


_DONCHIAN_SCHEMA = strategy_schema(
    strategy_id="donchian_breakout",
    name="Donchian Breakout",
    version="1.0.0",
    category="trend",
    description="Breakout above/below Donchian channel highs/lows.",
    warmup_bars=20,
    params=[
        {
            "name": "lookback",
            "type": "int",
            "min": 5,
            "max": 100,
            "default": 20,
            "step": 1,
            "description": "Donchian channel lookback.",
        },
        {
            "name": "exit_lookback",
            "type": "int",
            "min": 2,
            "max": 50,
            "default": 10,
            "step": 1,
            "description": "Exit channel lookback.",
        },
    ],
    inputs={"series": ["open", "high", "low", "close", "volume"]},
    tags=["trend", "breakout"],
)


def donchian_breakout_get_schema() -> dict[str, Any]:
    return copy.deepcopy(_DONCHIAN_SCHEMA)


def donchian_breakout_on_bar(ctx) -> dict[str, Any]:
    history, params, in_warmup, _ = prepare_context(ctx, _DONCHIAN_SCHEMA)
    lookback = int(params["lookback"])
    exit_lookback = int(params["exit_lookback"])
    if lookback <= 1 or exit_lookback <= 1:
        raise ValueError("strategy_params_invalid")
    warmup = max(lookback, exit_lookback, _DONCHIAN_SCHEMA["warmup_bars"])
    if len(history) <= warmup or in_warmup:
        return intent_response("HOLD", tags=["warmup"])

    high = numeric_series(history, "high")
    low = numeric_series(history, "low")
    close = numeric_series(history, "close")

    prev_high = float(high.iloc[-lookback - 1 : -1].max())
    prev_low = float(low.iloc[-lookback - 1 : -1].min())
    exit_high = float(high.iloc[-exit_lookback - 1 : -1].max())
    exit_low = float(low.iloc[-exit_lookback - 1 : -1].min())
    price = float(close.iloc[-1])

    if price > prev_high:
        return intent_response("ENTER_LONG", confidence=0.65, tags=["donchian_breakout_up"])
    if price < prev_low:
        return intent_response("ENTER_SHORT", confidence=0.65, tags=["donchian_breakout_down"])
    if price < exit_low:
        return intent_response("EXIT_LONG", confidence=0.4, tags=["donchian_exit_long"])
    if price > exit_high:
        return intent_response("EXIT_SHORT", confidence=0.4, tags=["donchian_exit_short"])
    return intent_response("HOLD")


DONCHIAN_BREAKOUT = BuiltinStrategyDefinition(
    strategy_id=_DONCHIAN_SCHEMA["id"],
    version=_DONCHIAN_SCHEMA["version"],
    get_schema=donchian_breakout_get_schema,
    on_bar=donchian_breakout_on_bar,
)


_BB_BREAKOUT_SCHEMA = strategy_schema(
    strategy_id="bollinger_breakout",
    name="Bollinger Breakout",
    version="1.0.0",
    category="trend",
    description="Breakout above/below Bollinger Bands.",
    warmup_bars=20,
    params=[
        {
            "name": "period",
            "type": "int",
            "min": 5,
            "max": 100,
            "default": 20,
            "step": 1,
            "description": "Bollinger lookback period.",
        },
        {
            "name": "k",
            "type": "float",
            "min": 1.0,
            "max": 3.5,
            "default": 2.0,
            "step": 0.1,
            "description": "Band width multiplier.",
        },
    ],
    inputs={"series": ["open", "high", "low", "close", "volume"]},
    tags=["trend", "breakout", "volatility"],
)


def bollinger_breakout_get_schema() -> dict[str, Any]:
    return copy.deepcopy(_BB_BREAKOUT_SCHEMA)


def bollinger_breakout_on_bar(ctx) -> dict[str, Any]:
    history, params, in_warmup, _ = prepare_context(ctx, _BB_BREAKOUT_SCHEMA)
    period = int(params["period"])
    k = float(params["k"])
    warmup = max(period, _BB_BREAKOUT_SCHEMA["warmup_bars"])
    if len(history) < warmup or in_warmup:
        return intent_response("HOLD", tags=["warmup"])

    close = numeric_series(history, "close")
    bands = bollinger_bands(close, period=period, k=k)
    upper = bands["upper"].iloc[-1]
    lower = bands["lower"].iloc[-1]
    mid = bands["mid"].iloc[-1]
    price = float(close.iloc[-1])

    if price > upper:
        return intent_response("ENTER_LONG", confidence=0.6, tags=["bb_breakout_up"])
    if price < lower:
        return intent_response("ENTER_SHORT", confidence=0.6, tags=["bb_breakout_down"])
    if price < mid:
        return intent_response("EXIT_LONG", confidence=0.4, tags=["bb_mid_exit_long"])
    if price > mid:
        return intent_response("EXIT_SHORT", confidence=0.4, tags=["bb_mid_exit_short"])
    return intent_response("HOLD")


BOLLINGER_BREAKOUT = BuiltinStrategyDefinition(
    strategy_id=_BB_BREAKOUT_SCHEMA["id"],
    version=_BB_BREAKOUT_SCHEMA["version"],
    get_schema=bollinger_breakout_get_schema,
    on_bar=bollinger_breakout_on_bar,
)


_SUPERTREND_SCHEMA = strategy_schema(
    strategy_id="supertrend_trend_follow",
    name="Supertrend Trend Follow",
    version="1.0.0",
    category="trend",
    description="Supertrend trend-following flips.",
    warmup_bars=20,
    params=[
        {
            "name": "atr_period",
            "type": "int",
            "min": 3,
            "max": 50,
            "default": 10,
            "step": 1,
            "description": "ATR lookback.",
        },
        {
            "name": "multiplier",
            "type": "float",
            "min": 1.0,
            "max": 5.0,
            "default": 3.0,
            "step": 0.1,
            "description": "Supertrend multiplier.",
        },
    ],
    inputs={"series": ["open", "high", "low", "close", "volume"]},
    tags=["trend", "supertrend"],
)


def supertrend_trend_follow_get_schema() -> dict[str, Any]:
    return copy.deepcopy(_SUPERTREND_SCHEMA)


def supertrend_trend_follow_on_bar(ctx) -> dict[str, Any]:
    history, params, in_warmup, _ = prepare_context(ctx, _SUPERTREND_SCHEMA)
    atr_period = int(params["atr_period"])
    multiplier = float(params["multiplier"])
    warmup = max(atr_period + 1, _SUPERTREND_SCHEMA["warmup_bars"])
    if len(history) < warmup or in_warmup:
        return intent_response("HOLD", tags=["warmup"])

    high = numeric_series(history, "high")
    low = numeric_series(history, "low")
    close = numeric_series(history, "close")
    st = supertrend(high, low, close, period=atr_period, multiplier=multiplier)
    pair_trend = last_two(st["trend"])
    if pair_trend is None:
        return intent_response("HOLD", tags=["insufficient_history"])
    prev_trend, curr_trend = pair_trend
    if prev_trend < 0 and curr_trend > 0:
        return intent_response("ENTER_LONG", confidence=0.7, tags=["supertrend_flip_up"])
    if prev_trend > 0 and curr_trend < 0:
        return intent_response("ENTER_SHORT", confidence=0.7, tags=["supertrend_flip_down"])
    return intent_response("HOLD")


SUPERTREND_TREND_FOLLOW = BuiltinStrategyDefinition(
    strategy_id=_SUPERTREND_SCHEMA["id"],
    version=_SUPERTREND_SCHEMA["version"],
    get_schema=supertrend_trend_follow_get_schema,
    on_bar=supertrend_trend_follow_on_bar,
)


_ADX_BREAKOUT_SCHEMA = strategy_schema(
    strategy_id="adx_filtered_breakout",
    name="ADX Filtered Breakout",
    version="1.0.0",
    category="trend",
    description="Donchian breakout filtered by ADX strength.",
    warmup_bars=28,
    params=[
        {
            "name": "lookback",
            "type": "int",
            "min": 5,
            "max": 100,
            "default": 20,
            "step": 1,
            "description": "Breakout lookback.",
        },
        {
            "name": "exit_lookback",
            "type": "int",
            "min": 2,
            "max": 50,
            "default": 10,
            "step": 1,
            "description": "Exit channel lookback.",
        },
        {
            "name": "adx_period",
            "type": "int",
            "min": 5,
            "max": 50,
            "default": 14,
            "step": 1,
            "description": "ADX lookback.",
        },
        {
            "name": "adx_threshold",
            "type": "float",
            "min": 5.0,
            "max": 50.0,
            "default": 20.0,
            "step": 0.5,
            "description": "Minimum ADX for breakout.",
        },
    ],
    inputs={"series": ["open", "high", "low", "close", "volume"]},
    tags=["trend", "breakout", "adx"],
)


def adx_filtered_breakout_get_schema() -> dict[str, Any]:
    return copy.deepcopy(_ADX_BREAKOUT_SCHEMA)


def adx_filtered_breakout_on_bar(ctx) -> dict[str, Any]:
    history, params, in_warmup, _ = prepare_context(ctx, _ADX_BREAKOUT_SCHEMA)
    lookback = int(params["lookback"])
    exit_lookback = int(params["exit_lookback"])
    adx_period = int(params["adx_period"])
    adx_threshold = float(params["adx_threshold"])
    warmup = max(lookback, exit_lookback, adx_period * 2, _ADX_BREAKOUT_SCHEMA["warmup_bars"])
    if len(history) <= warmup or in_warmup:
        return intent_response("HOLD", tags=["warmup"])

    high = numeric_series(history, "high")
    low = numeric_series(history, "low")
    close = numeric_series(history, "close")

    adx_df = adx_wilder(high, low, close, period=adx_period)
    adx_value = adx_df["adx"].iloc[-1]
    if adx_value is None or adx_value != adx_value:
        return intent_response("HOLD", tags=["adx_not_ready"])

    prev_high = float(high.iloc[-lookback - 1 : -1].max())
    prev_low = float(low.iloc[-lookback - 1 : -1].min())
    exit_high = float(high.iloc[-exit_lookback - 1 : -1].max())
    exit_low = float(low.iloc[-exit_lookback - 1 : -1].min())
    price = float(close.iloc[-1])

    if adx_value >= adx_threshold and price > prev_high:
        return intent_response("ENTER_LONG", confidence=0.7, tags=["adx_breakout_up"])
    if adx_value >= adx_threshold and price < prev_low:
        return intent_response("ENTER_SHORT", confidence=0.7, tags=["adx_breakout_down"])
    if price < exit_low:
        return intent_response("EXIT_LONG", confidence=0.4, tags=["adx_exit_long"])
    if price > exit_high:
        return intent_response("EXIT_SHORT", confidence=0.4, tags=["adx_exit_short"])
    return intent_response("HOLD")


ADX_FILTERED_BREAKOUT = BuiltinStrategyDefinition(
    strategy_id=_ADX_BREAKOUT_SCHEMA["id"],
    version=_ADX_BREAKOUT_SCHEMA["version"],
    get_schema=adx_filtered_breakout_get_schema,
    on_bar=adx_filtered_breakout_on_bar,
)


__all__ = [
    "ADX_FILTERED_BREAKOUT",
    "BOLLINGER_BREAKOUT",
    "DONCHIAN_BREAKOUT",
    "EMA_CROSSOVER",
    "SMA_CROSSOVER",
    "SUPERTREND_TREND_FOLLOW",
]

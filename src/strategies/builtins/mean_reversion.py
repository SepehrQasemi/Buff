from __future__ import annotations

import copy
from typing import Any

from strategies.builtins.common import (
    BuiltinStrategyDefinition,
    bollinger_bands,
    intent_response,
    keltner_channels,
    last_value,
    numeric_series,
    prepare_context,
    rsi_wilder,
    strategy_schema,
    zscore_series,
)


_RSI_SCHEMA = strategy_schema(
    strategy_id="rsi_mean_reversion",
    name="RSI Mean Reversion",
    version="1.0.0",
    category="mean-reversion",
    description="RSI oversold/overbought mean reversion.",
    warmup_bars=14,
    params=[
        {
            "name": "period",
            "type": "int",
            "min": 5,
            "max": 50,
            "default": 14,
            "step": 1,
            "description": "RSI lookback.",
        },
        {
            "name": "lower",
            "type": "float",
            "min": 5.0,
            "max": 45.0,
            "default": 30.0,
            "step": 0.5,
            "description": "Oversold threshold.",
        },
        {
            "name": "upper",
            "type": "float",
            "min": 55.0,
            "max": 95.0,
            "default": 70.0,
            "step": 0.5,
            "description": "Overbought threshold.",
        },
        {
            "name": "exit",
            "type": "float",
            "min": 40.0,
            "max": 60.0,
            "default": 50.0,
            "step": 0.5,
            "description": "Exit threshold toward mean.",
        },
    ],
    inputs={"series": ["open", "high", "low", "close", "volume"]},
    tags=["mean-reversion", "rsi"],
)


def rsi_mean_reversion_get_schema() -> dict[str, Any]:
    return copy.deepcopy(_RSI_SCHEMA)


def rsi_mean_reversion_on_bar(ctx) -> dict[str, Any]:
    history, params, in_warmup, _ = prepare_context(ctx, _RSI_SCHEMA)
    period = int(params["period"])
    lower = float(params["lower"])
    upper = float(params["upper"])
    exit_level = float(params["exit"])
    if not (lower < exit_level < upper):
        raise ValueError("strategy_params_invalid")
    warmup = max(period, _RSI_SCHEMA["warmup_bars"])
    if len(history) < warmup or in_warmup:
        return intent_response("HOLD", tags=["warmup"])

    close = numeric_series(history, "close")
    rsi = rsi_wilder(close, period=period)
    value = last_value(rsi)
    if value is None:
        return intent_response("HOLD", tags=["insufficient_history"])

    if value <= lower:
        return intent_response("ENTER_LONG", confidence=0.6, tags=["rsi_oversold"])
    if value >= upper:
        return intent_response("ENTER_SHORT", confidence=0.6, tags=["rsi_overbought"])
    if value >= exit_level:
        return intent_response("EXIT_LONG", confidence=0.4, tags=["rsi_exit_long"])
    if value <= exit_level:
        return intent_response("EXIT_SHORT", confidence=0.4, tags=["rsi_exit_short"])
    return intent_response("HOLD")


RSI_MEAN_REVERSION = BuiltinStrategyDefinition(
    strategy_id=_RSI_SCHEMA["id"],
    version=_RSI_SCHEMA["version"],
    get_schema=rsi_mean_reversion_get_schema,
    on_bar=rsi_mean_reversion_on_bar,
)


_BB_REVERSION_SCHEMA = strategy_schema(
    strategy_id="bollinger_reversion",
    name="Bollinger Reversion",
    version="1.0.0",
    category="mean-reversion",
    description="Mean reversion from Bollinger Bands back to midline.",
    warmup_bars=20,
    params=[
        {
            "name": "period",
            "type": "int",
            "min": 5,
            "max": 100,
            "default": 20,
            "step": 1,
            "description": "Bollinger lookback.",
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
    tags=["mean-reversion", "bollinger"],
)


def bollinger_reversion_get_schema() -> dict[str, Any]:
    return copy.deepcopy(_BB_REVERSION_SCHEMA)


def bollinger_reversion_on_bar(ctx) -> dict[str, Any]:
    history, params, in_warmup, _ = prepare_context(ctx, _BB_REVERSION_SCHEMA)
    period = int(params["period"])
    k = float(params["k"])
    warmup = max(period, _BB_REVERSION_SCHEMA["warmup_bars"])
    if len(history) < warmup or in_warmup:
        return intent_response("HOLD", tags=["warmup"])

    close = numeric_series(history, "close")
    bands = bollinger_bands(close, period=period, k=k)
    upper = bands["upper"].iloc[-1]
    lower = bands["lower"].iloc[-1]
    mid = bands["mid"].iloc[-1]
    price = float(close.iloc[-1])

    if price < lower:
        return intent_response("ENTER_LONG", confidence=0.55, tags=["bb_reversion_long"])
    if price > upper:
        return intent_response("ENTER_SHORT", confidence=0.55, tags=["bb_reversion_short"])
    if price >= mid:
        return intent_response("EXIT_LONG", confidence=0.4, tags=["bb_mid_exit_long"])
    if price <= mid:
        return intent_response("EXIT_SHORT", confidence=0.4, tags=["bb_mid_exit_short"])
    return intent_response("HOLD")


BOLLINGER_REVERSION = BuiltinStrategyDefinition(
    strategy_id=_BB_REVERSION_SCHEMA["id"],
    version=_BB_REVERSION_SCHEMA["version"],
    get_schema=bollinger_reversion_get_schema,
    on_bar=bollinger_reversion_on_bar,
)


_ZSCORE_SCHEMA = strategy_schema(
    strategy_id="zscore_reversion",
    name="Z-score Reversion",
    version="1.0.0",
    category="mean-reversion",
    description="Price z-score mean reversion.",
    warmup_bars=20,
    params=[
        {
            "name": "lookback",
            "type": "int",
            "min": 10,
            "max": 100,
            "default": 20,
            "step": 1,
            "description": "Z-score rolling window.",
        },
        {
            "name": "entry_z",
            "type": "float",
            "min": 1.0,
            "max": 4.0,
            "default": 2.0,
            "step": 0.1,
            "description": "Entry threshold (absolute z).",
        },
        {
            "name": "exit_z",
            "type": "float",
            "min": 0.1,
            "max": 2.0,
            "default": 0.5,
            "step": 0.1,
            "description": "Exit threshold (absolute z).",
        },
    ],
    inputs={"series": ["open", "high", "low", "close", "volume"]},
    tags=["mean-reversion", "statistics"],
)


def zscore_reversion_get_schema() -> dict[str, Any]:
    return copy.deepcopy(_ZSCORE_SCHEMA)


def zscore_reversion_on_bar(ctx) -> dict[str, Any]:
    history, params, in_warmup, _ = prepare_context(ctx, _ZSCORE_SCHEMA)
    lookback = int(params["lookback"])
    entry_z = float(params["entry_z"])
    exit_z = float(params["exit_z"])
    if exit_z >= entry_z:
        raise ValueError("strategy_params_invalid")
    warmup = max(lookback, _ZSCORE_SCHEMA["warmup_bars"])
    if len(history) < warmup or in_warmup:
        return intent_response("HOLD", tags=["warmup"])

    close = numeric_series(history, "close")
    zscore = zscore_series(close, period=lookback)
    value = last_value(zscore)
    if value is None:
        return intent_response("HOLD", tags=["insufficient_history"])

    if value <= -entry_z:
        return intent_response("ENTER_LONG", confidence=0.6, tags=["zscore_low"])
    if value >= entry_z:
        return intent_response("ENTER_SHORT", confidence=0.6, tags=["zscore_high"])
    if value >= -exit_z:
        return intent_response("EXIT_LONG", confidence=0.4, tags=["zscore_exit_long"])
    if value <= exit_z:
        return intent_response("EXIT_SHORT", confidence=0.4, tags=["zscore_exit_short"])
    return intent_response("HOLD")


ZSCORE_REVERSION = BuiltinStrategyDefinition(
    strategy_id=_ZSCORE_SCHEMA["id"],
    version=_ZSCORE_SCHEMA["version"],
    get_schema=zscore_reversion_get_schema,
    on_bar=zscore_reversion_on_bar,
)


_KELTNER_SCHEMA = strategy_schema(
    strategy_id="keltner_reversion",
    name="Keltner Reversion",
    version="1.0.0",
    category="mean-reversion",
    description="Reversion from Keltner channel extremes to midline.",
    warmup_bars=20,
    params=[
        {
            "name": "ema_period",
            "type": "int",
            "min": 5,
            "max": 100,
            "default": 20,
            "step": 1,
            "description": "EMA midline lookback.",
        },
        {
            "name": "atr_period",
            "type": "int",
            "min": 5,
            "max": 100,
            "default": 20,
            "step": 1,
            "description": "ATR lookback.",
        },
        {
            "name": "atr_mult",
            "type": "float",
            "min": 0.5,
            "max": 3.0,
            "default": 1.5,
            "step": 0.1,
            "description": "ATR multiplier for channel width.",
        },
    ],
    inputs={"series": ["open", "high", "low", "close", "volume"]},
    tags=["mean-reversion", "keltner"],
)


def keltner_reversion_get_schema() -> dict[str, Any]:
    return copy.deepcopy(_KELTNER_SCHEMA)


def keltner_reversion_on_bar(ctx) -> dict[str, Any]:
    history, params, in_warmup, _ = prepare_context(ctx, _KELTNER_SCHEMA)
    ema_period = int(params["ema_period"])
    atr_period = int(params["atr_period"])
    atr_mult = float(params["atr_mult"])
    warmup = max(ema_period, atr_period, _KELTNER_SCHEMA["warmup_bars"])
    if len(history) < warmup or in_warmup:
        return intent_response("HOLD", tags=["warmup"])

    high = numeric_series(history, "high")
    low = numeric_series(history, "low")
    close = numeric_series(history, "close")
    kc = keltner_channels(
        high, low, close, ema_period=ema_period, atr_period=atr_period, atr_mult=atr_mult
    )
    upper = kc["upper"].iloc[-1]
    lower = kc["lower"].iloc[-1]
    mid = kc["mid"].iloc[-1]
    price = float(close.iloc[-1])

    if price < lower:
        return intent_response("ENTER_LONG", confidence=0.55, tags=["keltner_reversion_long"])
    if price > upper:
        return intent_response("ENTER_SHORT", confidence=0.55, tags=["keltner_reversion_short"])
    if price >= mid:
        return intent_response("EXIT_LONG", confidence=0.4, tags=["keltner_exit_long"])
    if price <= mid:
        return intent_response("EXIT_SHORT", confidence=0.4, tags=["keltner_exit_short"])
    return intent_response("HOLD")


KELTNER_REVERSION = BuiltinStrategyDefinition(
    strategy_id=_KELTNER_SCHEMA["id"],
    version=_KELTNER_SCHEMA["version"],
    get_schema=keltner_reversion_get_schema,
    on_bar=keltner_reversion_on_bar,
)


__all__ = [
    "BOLLINGER_REVERSION",
    "KELTNER_REVERSION",
    "RSI_MEAN_REVERSION",
    "ZSCORE_REVERSION",
]

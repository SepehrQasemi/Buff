from __future__ import annotations

import copy
from typing import Any

from strategies.builtins.common import (
    BuiltinStrategyDefinition,
    atr_wilder,
    bollinger_bands,
    intent_response,
    keltner_channels,
    numeric_series,
    prepare_context,
    strategy_schema,
)


_ATR_BREAKOUT_SCHEMA = strategy_schema(
    strategy_id="atr_volatility_breakout",
    name="ATR Volatility Breakout",
    version="1.0.0",
    category="volatility",
    description="Breakout with ATR percent filter.",
    warmup_bars=20,
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
            "description": "Exit lookback.",
        },
        {
            "name": "atr_period",
            "type": "int",
            "min": 5,
            "max": 50,
            "default": 14,
            "step": 1,
            "description": "ATR lookback.",
        },
        {
            "name": "atr_pct_threshold",
            "type": "float",
            "min": 0.002,
            "max": 0.05,
            "default": 0.01,
            "step": 0.001,
            "description": "Minimum ATR percent for breakout.",
        },
    ],
    inputs={"series": ["open", "high", "low", "close", "volume"]},
    tags=["volatility", "breakout"],
)


def atr_volatility_breakout_get_schema() -> dict[str, Any]:
    return copy.deepcopy(_ATR_BREAKOUT_SCHEMA)


def atr_volatility_breakout_on_bar(ctx) -> dict[str, Any]:
    history, params, in_warmup, _ = prepare_context(ctx, _ATR_BREAKOUT_SCHEMA)
    lookback = int(params["lookback"])
    exit_lookback = int(params["exit_lookback"])
    atr_period = int(params["atr_period"])
    atr_pct_threshold = float(params["atr_pct_threshold"])
    warmup = max(lookback, exit_lookback, atr_period, _ATR_BREAKOUT_SCHEMA["warmup_bars"])
    if len(history) <= warmup or in_warmup:
        return intent_response("HOLD", tags=["warmup"])

    high = numeric_series(history, "high")
    low = numeric_series(history, "low")
    close = numeric_series(history, "close")

    atr = atr_wilder(high, low, close, period=atr_period)
    atr_pct = float(atr.iloc[-1]) / float(close.iloc[-1])

    prev_high = float(high.iloc[-lookback - 1 : -1].max())
    prev_low = float(low.iloc[-lookback - 1 : -1].min())
    exit_high = float(high.iloc[-exit_lookback - 1 : -1].max())
    exit_low = float(low.iloc[-exit_lookback - 1 : -1].min())
    price = float(close.iloc[-1])

    if atr_pct >= atr_pct_threshold and price > prev_high:
        return intent_response("ENTER_LONG", confidence=0.7, tags=["atr_breakout_up"])
    if atr_pct >= atr_pct_threshold and price < prev_low:
        return intent_response("ENTER_SHORT", confidence=0.7, tags=["atr_breakout_down"])
    if price < exit_low:
        return intent_response("EXIT_LONG", confidence=0.4, tags=["atr_exit_long"])
    if price > exit_high:
        return intent_response("EXIT_SHORT", confidence=0.4, tags=["atr_exit_short"])
    return intent_response("HOLD")


ATR_VOLATILITY_BREAKOUT = BuiltinStrategyDefinition(
    strategy_id=_ATR_BREAKOUT_SCHEMA["id"],
    version=_ATR_BREAKOUT_SCHEMA["version"],
    get_schema=atr_volatility_breakout_get_schema,
    on_bar=atr_volatility_breakout_on_bar,
)


_SQUEEZE_SCHEMA = strategy_schema(
    strategy_id="bb_keltner_squeeze_release",
    name="BB-Keltner Squeeze Release",
    version="1.0.0",
    category="volatility",
    description="Bollinger squeeze inside Keltner and release breakout.",
    warmup_bars=25,
    params=[
        {
            "name": "bb_period",
            "type": "int",
            "min": 5,
            "max": 100,
            "default": 20,
            "step": 1,
            "description": "Bollinger lookback.",
        },
        {
            "name": "bb_k",
            "type": "float",
            "min": 1.0,
            "max": 3.5,
            "default": 2.0,
            "step": 0.1,
            "description": "Bollinger band width.",
        },
        {
            "name": "kc_period",
            "type": "int",
            "min": 5,
            "max": 100,
            "default": 20,
            "step": 1,
            "description": "Keltner EMA/ATR lookback.",
        },
        {
            "name": "kc_atr_mult",
            "type": "float",
            "min": 0.5,
            "max": 3.0,
            "default": 1.5,
            "step": 0.1,
            "description": "Keltner ATR multiplier.",
        },
        {
            "name": "squeeze_bars",
            "type": "int",
            "min": 2,
            "max": 20,
            "default": 5,
            "step": 1,
            "description": "Minimum consecutive squeeze bars.",
        },
    ],
    inputs={"series": ["open", "high", "low", "close", "volume"]},
    tags=["volatility", "squeeze"],
)


def bb_keltner_squeeze_release_get_schema() -> dict[str, Any]:
    return copy.deepcopy(_SQUEEZE_SCHEMA)


def bb_keltner_squeeze_release_on_bar(ctx) -> dict[str, Any]:
    history, params, in_warmup, _ = prepare_context(ctx, _SQUEEZE_SCHEMA)
    bb_period = int(params["bb_period"])
    bb_k = float(params["bb_k"])
    kc_period = int(params["kc_period"])
    kc_atr_mult = float(params["kc_atr_mult"])
    squeeze_bars = int(params["squeeze_bars"])
    warmup = max(bb_period, kc_period, squeeze_bars, _SQUEEZE_SCHEMA["warmup_bars"])
    if len(history) < warmup or in_warmup:
        return intent_response("HOLD", tags=["warmup"])

    high = numeric_series(history, "high")
    low = numeric_series(history, "low")
    close = numeric_series(history, "close")

    bb = bollinger_bands(close, period=bb_period, k=bb_k)
    kc = keltner_channels(
        high, low, close, ema_period=kc_period, atr_period=kc_period, atr_mult=kc_atr_mult
    )

    squeeze = (bb["upper"] < kc["upper"]) & (bb["lower"] > kc["lower"])
    if len(squeeze) < squeeze_bars + 1:
        return intent_response("HOLD", tags=["insufficient_history"])

    prior_squeeze = squeeze.iloc[-(squeeze_bars + 1) : -1].all()
    current_squeeze = bool(squeeze.iloc[-1])
    if not prior_squeeze or current_squeeze:
        return intent_response("HOLD")

    price = float(close.iloc[-1])
    upper = float(bb["upper"].iloc[-1])
    lower = float(bb["lower"].iloc[-1])
    mid = float(bb["mid"].iloc[-1])

    if price > upper:
        return intent_response("ENTER_LONG", confidence=0.7, tags=["squeeze_release_up"])
    if price < lower:
        return intent_response("ENTER_SHORT", confidence=0.7, tags=["squeeze_release_down"])
    if price < mid:
        return intent_response("EXIT_LONG", confidence=0.4, tags=["squeeze_exit_long"])
    if price > mid:
        return intent_response("EXIT_SHORT", confidence=0.4, tags=["squeeze_exit_short"])
    return intent_response("HOLD")


BB_KELTNER_SQUEEZE_RELEASE = BuiltinStrategyDefinition(
    strategy_id=_SQUEEZE_SCHEMA["id"],
    version=_SQUEEZE_SCHEMA["version"],
    get_schema=bb_keltner_squeeze_release_get_schema,
    on_bar=bb_keltner_squeeze_release_on_bar,
)


__all__ = ["ATR_VOLATILITY_BREAKOUT", "BB_KELTNER_SQUEEZE_RELEASE"]

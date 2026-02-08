from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from buff.features.indicators import (
    adx_wilder,
    atr_wilder,
    bollinger_bands,
    ema,
    macd,
    roc,
    rolling_std,
    rsi_wilder,
    sma,
)


ALLOWED_INTENTS = {
    "HOLD",
    "ENTER_LONG",
    "ENTER_SHORT",
    "EXIT_LONG",
    "EXIT_SHORT",
}

ALLOWED_CATEGORIES = {
    "trend",
    "mean-reversion",
    "momentum",
    "volatility",
    "structure",
    "wrapper",
}

SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


@dataclass(frozen=True)
class PositionState:
    side: str
    entry_price: float
    entry_index: int
    max_price: float
    min_price: float
    bars_in_trade: int


@dataclass(frozen=True)
class StrategyContext:
    history: pd.DataFrame
    params: Mapping[str, Any]
    position: PositionState | None = None
    indicators: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class BuiltinStrategyDefinition:
    strategy_id: str
    version: str
    get_schema: Callable[[], dict[str, Any]]
    on_bar: Callable[[StrategyContext | Mapping[str, Any]], dict[str, Any]]


def is_semver(value: str) -> bool:
    if not isinstance(value, str):
        return False
    return SEMVER_RE.match(value) is not None


def intent_response(
    intent: str,
    *,
    confidence: float | None = None,
    tags: Sequence[str] | None = None,
) -> dict[str, Any]:
    if intent not in ALLOWED_INTENTS:
        raise ValueError("strategy_intent_invalid")
    payload: dict[str, Any] = {"intent": intent}
    if confidence is not None:
        payload["confidence"] = float(confidence)
    if tags is not None:
        payload["tags"] = list(tags)
    return payload


def strategy_schema(
    *,
    strategy_id: str,
    name: str,
    version: str,
    category: str,
    description: str,
    warmup_bars: int,
    params: Sequence[Mapping[str, Any]],
    inputs: Mapping[str, Any],
    tags: Sequence[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": strategy_id,
        "name": name,
        "version": version,
        "category": category,
        "description": description,
        "warmup_bars": int(warmup_bars),
        "inputs": dict(inputs),
        "params": [dict(item) for item in params],
        "outputs": {
            "intents": sorted(ALLOWED_INTENTS),
            "provides_confidence": True,
            "provides_tags": True,
        },
        "tags": list(tags or []),
    }


def _coerce_history(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value
    raise ValueError("strategy_history_invalid")


def _coerce_params(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return value
    raise ValueError("strategy_params_invalid")


def _coerce_position(value: Any, history_len: int) -> PositionState | None:
    if value is None:
        return None
    if isinstance(value, PositionState):
        return value
    if not isinstance(value, Mapping):
        raise ValueError("strategy_position_invalid")
    side = str(value.get("side", ""))
    if side not in {"LONG", "SHORT"}:
        raise ValueError("strategy_position_invalid")
    entry_price = float(value.get("entry_price", 0.0))
    entry_index = int(value.get("entry_index", 0))
    max_price = float(value.get("max_price", entry_price))
    min_price = float(value.get("min_price", entry_price))
    bars_in_trade = value.get("bars_in_trade")
    if bars_in_trade is None:
        bars_in_trade = max(0, history_len - entry_index - 1)
    bars_in_trade = int(bars_in_trade)
    return PositionState(
        side=side,
        entry_price=entry_price,
        entry_index=entry_index,
        max_price=max_price,
        min_price=min_price,
        bars_in_trade=bars_in_trade,
    )


def extract_context(ctx: StrategyContext | Mapping[str, Any]) -> StrategyContext:
    if isinstance(ctx, StrategyContext):
        return ctx
    if not isinstance(ctx, Mapping):
        raise ValueError("strategy_context_invalid")
    history = _coerce_history(ctx.get("history"))
    params = _coerce_params(ctx.get("params"))
    position = _coerce_position(ctx.get("position"), len(history))
    indicators = ctx.get("indicators")
    if indicators is not None and not isinstance(indicators, Mapping):
        raise ValueError("strategy_indicators_invalid")
    return StrategyContext(
        history=history,
        params=params,
        position=position,
        indicators=indicators,
    )


def validate_history(
    history: pd.DataFrame, *, required: Sequence[str] | None = None
) -> pd.DataFrame:
    required_columns = set(required or ["open", "high", "low", "close", "volume"])
    if not required_columns.issubset(set(history.columns)):
        missing = sorted(required_columns - set(history.columns))
        raise ValueError(f"strategy_history_missing_columns:{','.join(missing)}")
    if history.empty:
        raise ValueError("strategy_history_empty")
    if not history.index.is_monotonic_increasing:
        history = history.sort_index()
    return history


def numeric_series(history: pd.DataFrame, name: str) -> pd.Series:
    if name not in history.columns:
        raise ValueError(f"strategy_history_missing_columns:{name}")
    series = pd.to_numeric(history[name], errors="coerce")
    if not math.isfinite(float(series.iloc[-1])):
        raise ValueError("strategy_history_invalid")
    return series


def resolve_params(
    schema_params: Sequence[Mapping[str, Any]],
    provided: Mapping[str, Any] | None,
) -> dict[str, Any]:
    params = _coerce_params(provided)
    allowed = {spec.get("name") for spec in schema_params}
    for key in params.keys():
        if key not in allowed:
            raise ValueError("strategy_params_unknown")
    resolved: dict[str, Any] = {}
    for spec in schema_params:
        name = spec.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("strategy_schema_invalid")
        if name in params:
            value = params.get(name)
        else:
            value = spec.get("default")
        resolved[name] = _coerce_param_value(spec, value)
    return resolved


def _coerce_param_value(spec: Mapping[str, Any], value: Any) -> Any:
    param_type = spec.get("type")
    if param_type == "int":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("strategy_params_invalid")
        coerced: Any = int(value)
    elif param_type == "float":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("strategy_params_invalid")
        coerced = float(value)
    elif param_type == "bool":
        if not isinstance(value, bool):
            raise ValueError("strategy_params_invalid")
        coerced = bool(value)
    elif param_type == "string":
        if not isinstance(value, str):
            raise ValueError("strategy_params_invalid")
        coerced = value
    elif param_type == "enum":
        if not isinstance(value, str):
            raise ValueError("strategy_params_invalid")
        options = spec.get("enum")
        if not isinstance(options, Sequence):
            raise ValueError("strategy_params_invalid")
        if value not in options:
            raise ValueError("strategy_params_invalid")
        coerced = value
    else:
        raise ValueError("strategy_params_invalid")

    min_val = spec.get("min")
    if min_val is not None:
        if not isinstance(min_val, (int, float)) or isinstance(min_val, bool):
            raise ValueError("strategy_params_invalid")
        if coerced < min_val:
            raise ValueError("strategy_params_invalid")
    max_val = spec.get("max")
    if max_val is not None:
        if not isinstance(max_val, (int, float)) or isinstance(max_val, bool):
            raise ValueError("strategy_params_invalid")
        if coerced > max_val:
            raise ValueError("strategy_params_invalid")

    return coerced


def prepare_context(
    ctx: StrategyContext | Mapping[str, Any],
    schema: Mapping[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any], bool, PositionState | None]:
    context = extract_context(ctx)
    history = validate_history(context.history)
    params = resolve_params(schema.get("params", []), context.params)
    warmup_bars = int(schema.get("warmup_bars", 0))
    in_warmup = len(history) < warmup_bars
    return history, params, in_warmup, context.position


def last_two(series: pd.Series) -> tuple[float, float] | None:
    cleaned = pd.to_numeric(series, errors="coerce")
    if len(cleaned) < 2:
        return None
    prev = float(cleaned.iloc[-2])
    curr = float(cleaned.iloc[-1])
    if not math.isfinite(prev) or not math.isfinite(curr):
        return None
    return prev, curr


def last_value(series: pd.Series) -> float | None:
    cleaned = pd.to_numeric(series, errors="coerce")
    if cleaned.empty:
        return None
    curr = float(cleaned.iloc[-1])
    if not math.isfinite(curr):
        return None
    return curr


def rolling_max(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).max()


def rolling_min(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).min()


def donchian_channels(high: pd.Series, low: pd.Series, period: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "upper": rolling_max(high, period),
            "lower": rolling_min(low, period),
        }
    )


def keltner_channels(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    *,
    ema_period: int,
    atr_period: int,
    atr_mult: float,
) -> pd.DataFrame:
    mid = ema(close, period=ema_period)
    atr_val = atr_wilder(high, low, close, period=atr_period)
    upper = mid + atr_mult * atr_val
    lower = mid - atr_mult * atr_val
    return pd.DataFrame({"mid": mid, "upper": upper, "lower": lower})


def stochastic_kd(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    *,
    k_period: int,
    d_period: int,
    smooth_k: int,
) -> pd.DataFrame:
    highest = rolling_max(high, k_period)
    lowest = rolling_min(low, k_period)
    denom = (highest - lowest).replace(0.0, float("nan"))
    raw_k = 100.0 * (close - lowest) / denom
    if smooth_k > 1:
        k = raw_k.rolling(window=smooth_k, min_periods=smooth_k).mean()
    else:
        k = raw_k
    d = k.rolling(window=d_period, min_periods=d_period).mean()
    return pd.DataFrame({"k": k, "d": d})


def zscore_series(close: pd.Series, period: int) -> pd.Series:
    mean = close.rolling(window=period, min_periods=period).mean()
    std = rolling_std(close, period=period)
    denom = std.replace(0.0, float("nan"))
    return (close - mean) / denom


def supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    *,
    period: int,
    multiplier: float,
) -> pd.DataFrame:
    atr = atr_wilder(high, low, close, period=period)
    hl2 = (high + low) / 2.0
    upper = hl2 + multiplier * atr
    lower = hl2 - multiplier * atr

    final_upper = upper.copy()
    final_lower = lower.copy()
    trend = pd.Series(1, index=close.index, dtype=int)

    for i in range(1, len(close)):
        if not math.isfinite(float(upper.iloc[i])) or not math.isfinite(float(lower.iloc[i])):
            trend.iloc[i] = trend.iloc[i - 1]
            final_upper.iloc[i] = final_upper.iloc[i - 1]
            final_lower.iloc[i] = final_lower.iloc[i - 1]
            continue

        if upper.iloc[i] < final_upper.iloc[i - 1] or close.iloc[i - 1] > final_upper.iloc[i - 1]:
            final_upper.iloc[i] = upper.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[i - 1]

        if lower.iloc[i] > final_lower.iloc[i - 1] or close.iloc[i - 1] < final_lower.iloc[i - 1]:
            final_lower.iloc[i] = lower.iloc[i]
        else:
            final_lower.iloc[i] = final_lower.iloc[i - 1]

        if trend.iloc[i - 1] == -1 and close.iloc[i] > final_upper.iloc[i - 1]:
            trend.iloc[i] = 1
        elif trend.iloc[i - 1] == 1 and close.iloc[i] < final_lower.iloc[i - 1]:
            trend.iloc[i] = -1
        else:
            trend.iloc[i] = trend.iloc[i - 1]

        if trend.iloc[i] == 1 and final_lower.iloc[i] < final_lower.iloc[i - 1]:
            final_lower.iloc[i] = final_lower.iloc[i - 1]
        if trend.iloc[i] == -1 and final_upper.iloc[i] > final_upper.iloc[i - 1]:
            final_upper.iloc[i] = final_upper.iloc[i - 1]

    supertrend_line = final_lower.where(trend == 1, final_upper)
    return pd.DataFrame(
        {
            "trend": trend,
            "supertrend": supertrend_line,
            "upper": final_upper,
            "lower": final_lower,
        }
    )


def last_pivot_levels(
    high: pd.Series,
    low: pd.Series,
    lookback: int,
) -> tuple[float | None, float | None]:
    if lookback <= 0:
        return None, None
    pivot_high = None
    pivot_low = None
    end = len(high) - lookback
    for i in range(lookback, max(lookback, end)):
        window = high.iloc[i - lookback : i + lookback + 1]
        if len(window) < (lookback * 2 + 1):
            continue
        if high.iloc[i] == window.max():
            pivot_high = float(high.iloc[i])
    for i in range(lookback, max(lookback, end)):
        window = low.iloc[i - lookback : i + lookback + 1]
        if len(window) < (lookback * 2 + 1):
            continue
        if low.iloc[i] == window.min():
            pivot_low = float(low.iloc[i])
    return pivot_high, pivot_low


def update_position_extremes(position: PositionState, *, high: float, low: float) -> PositionState:
    max_price = max(position.max_price, high)
    min_price = min(position.min_price, low)
    bars_in_trade = position.bars_in_trade + 1
    return PositionState(
        side=position.side,
        entry_price=position.entry_price,
        entry_index=position.entry_index,
        max_price=max_price,
        min_price=min_price,
        bars_in_trade=bars_in_trade,
    )


__all__ = [
    "ALLOWED_CATEGORIES",
    "ALLOWED_INTENTS",
    "BuiltinStrategyDefinition",
    "PositionState",
    "StrategyContext",
    "adx_wilder",
    "atr_wilder",
    "bollinger_bands",
    "ema",
    "intent_response",
    "is_semver",
    "keltner_channels",
    "last_pivot_levels",
    "last_two",
    "last_value",
    "macd",
    "numeric_series",
    "prepare_context",
    "roc",
    "rolling_max",
    "rolling_min",
    "rsi_wilder",
    "sma",
    "stochastic_kd",
    "strategy_schema",
    "supertrend",
    "update_position_extremes",
    "validate_history",
    "zscore_series",
]

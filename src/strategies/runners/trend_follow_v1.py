from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from buff.features.indicators import atr_wilder, ema, rsi_wilder
from strategy_registry.decision import (
    DECISION_SCHEMA_VERSION,
    Decision,
    DecisionAction,
    DecisionProvenance,
    DecisionRisk,
    params_hash,
)
from strategy_registry.registry import StrategySpec


EMA_FAST = 20
EMA_SLOW = 50
RSI_PERIOD = 14
ATR_PERIOD = 14
RSI_ENTRY = 55.0
RSI_EXIT = 45.0
ATR_STOP_MULT = 2.0
ATR_TAKE_MULT = 4.0
RISK_PCT = 0.01
DEFAULT_EQUITY = 10_000.0
ATR_EPS = 1e-6
MAX_NOTIONAL = DEFAULT_EQUITY
MAX_POSITION_SIZE = 1_000.0


TREND_FOLLOW_V1_SPEC = StrategySpec(
    name="TREND_FOLLOW_V1",
    version="1.0.0",
    description="EMA20/EMA50 trend follow with RSI confirmation and ATR risk.",
    required_features=["ema_20@1", "ema_50@1", "rsi_14@1", "atr_14@1"],
    required_timeframes=["1m"],
    params={
        "ema_fast": EMA_FAST,
        "ema_slow": EMA_SLOW,
        "rsi_period": RSI_PERIOD,
        "atr_period": ATR_PERIOD,
        "rsi_entry": RSI_ENTRY,
        "rsi_exit": RSI_EXIT,
        "atr_stop_mult": ATR_STOP_MULT,
        "atr_take_mult": ATR_TAKE_MULT,
        "risk_pct": RISK_PCT,
        "equity": DEFAULT_EQUITY,
        "atr_eps": ATR_EPS,
        "max_notional": MAX_NOTIONAL,
        "max_position_size": MAX_POSITION_SIZE,
        "required_columns": ["close"],
    },
)


def _numeric_series(df: pd.DataFrame, name: str) -> pd.Series:
    if name not in df.columns:
        raise ValueError(f"strategy_missing_column:{name}")
    return pd.to_numeric(df[name], errors="coerce")


def _compute_indicators_from_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    close = _numeric_series(df, "close")
    high = _numeric_series(df, "high")
    low = _numeric_series(df, "low")
    out = pd.DataFrame(
        {
            "close": close,
            "ema_20": ema(close, period=EMA_FAST),
            "ema_50": ema(close, period=EMA_SLOW),
            "rsi_14": rsi_wilder(close, period=RSI_PERIOD),
            "atr_14": atr_wilder(high, low, close, period=ATR_PERIOD),
        },
        index=df.index,
    )
    return out


def _load_indicators(features_df: pd.DataFrame) -> pd.DataFrame:
    columns = {"close", "ema_20", "ema_50", "rsi_14", "atr_14"}
    if "close" not in features_df.columns:
        raise ValueError("strategy_missing_column:close")
    if columns.issubset(set(features_df.columns)):
        ordered = ["close", "ema_20", "ema_50", "rsi_14", "atr_14"]
        return features_df[ordered].copy()
    return _compute_indicators_from_ohlcv(features_df)


def _validate_required_columns(features_df: pd.DataFrame) -> None:
    if "close" not in features_df.columns:
        raise ValueError("strategy_missing_column:close")
    required_indicators = {"ema_20", "ema_50", "rsi_14", "atr_14"}
    if required_indicators.issubset(set(features_df.columns)):
        return
    if not {"high", "low"}.issubset(set(features_df.columns)):
        missing = sorted(required_indicators - set(features_df.columns))
        raise ValueError(f"strategy_missing_columns:{','.join(missing)}")


def _latest_two_rows(indicators: pd.DataFrame) -> pd.DataFrame:
    cleaned = indicators.apply(pd.to_numeric, errors="coerce").dropna()
    if len(cleaned) < 2:
        raise ValueError("strategy_insufficient_history")
    return cleaned.iloc[-2:]


def _decision_action(latest: pd.DataFrame) -> tuple[DecisionAction, dict[str, bool]]:
    prev = latest.iloc[0]
    curr = latest.iloc[1]

    ema_cross_up = prev["ema_20"] <= prev["ema_50"] and curr["ema_20"] > curr["ema_50"]
    ema_cross_down = prev["ema_20"] >= prev["ema_50"] and curr["ema_20"] < curr["ema_50"]

    rsi_entry = curr["rsi_14"] > RSI_ENTRY
    rsi_exit = curr["rsi_14"] < RSI_EXIT

    entry_signal = ema_cross_up and rsi_entry
    exit_signal = ema_cross_down or rsi_exit

    if entry_signal:
        action = DecisionAction.ENTER_LONG
    elif exit_signal:
        action = DecisionAction.EXIT_LONG
    else:
        action = DecisionAction.HOLD

    return action, {
        "ema_cross_up": bool(ema_cross_up),
        "ema_cross_down": bool(ema_cross_down),
        "rsi_entry": bool(rsi_entry),
        "rsi_exit": bool(rsi_exit),
    }


def _risk_fields(latest: pd.Series) -> tuple[DecisionRisk, float]:
    entry_price = float(latest["close"])
    atr = float(latest["atr_14"])
    if entry_price <= 0.0 or not pd.notna(entry_price):
        raise ValueError("strategy_invalid_price_or_atr")
    if not pd.notna(atr):
        raise ValueError("strategy_invalid_price_or_atr")

    atr_eff = max(atr, ATR_EPS)
    stop_distance = ATR_STOP_MULT * atr_eff
    risk_dollars = DEFAULT_EQUITY * RISK_PCT
    position_size = risk_dollars / stop_distance
    max_by_notional = MAX_NOTIONAL / entry_price
    position_size = min(position_size, max_by_notional, MAX_POSITION_SIZE)
    stop_loss = entry_price - stop_distance
    take_profit = entry_price + (ATR_TAKE_MULT * atr_eff)

    risk = DecisionRisk(
        max_position_size=position_size,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )
    return risk, entry_price


def _rationale(latest: pd.DataFrame, signals: Mapping[str, bool], entry_price: float) -> list[str]:
    prev = latest.iloc[0]
    curr = latest.iloc[1]
    return [
        f"signals={dict(signals)}",
        (
            "indicators="
            f"ema_20_prev={prev['ema_20']:.6f},ema_50_prev={prev['ema_50']:.6f},"
            f"ema_20={curr['ema_20']:.6f},ema_50={curr['ema_50']:.6f},"
            f"rsi_14={curr['rsi_14']:.6f},atr_14={curr['atr_14']:.6f},"
            f"close={curr['close']:.6f}"
        ),
        (
            "thresholds="
            f"ema_fast={EMA_FAST},ema_slow={EMA_SLOW},"
            f"rsi_entry>{RSI_ENTRY},rsi_exit<{RSI_EXIT},"
            f"atr_stop_mult={ATR_STOP_MULT},atr_take_mult={ATR_TAKE_MULT}"
        ),
        f"position_sizing=equity:{DEFAULT_EQUITY},risk_pct:{RISK_PCT},entry_price:{entry_price:.6f}",
    ]


def _bundle_fingerprint(metadata: Any) -> str:
    if isinstance(metadata, Mapping):
        return str(metadata.get("bundle_fingerprint", ""))
    return str(getattr(metadata, "bundle_fingerprint", ""))


def _instrument(features_df: pd.DataFrame, metadata: Any) -> str:
    value = features_df.attrs.get("instrument")
    if isinstance(value, str) and value:
        return value
    if isinstance(metadata, Mapping):
        value = metadata.get("instrument")
        if isinstance(value, str):
            return value
        return ""
    return str(getattr(metadata, "instrument", ""))


def _filter_to_as_of(features_df: pd.DataFrame, as_of_utc: str) -> pd.DataFrame:
    try:
        as_of_ts = pd.to_datetime(as_of_utc, utc=True)
    except Exception as exc:
        raise ValueError("strategy_as_of_invalid") from exc

    if "timestamp" in features_df.columns:
        ts = pd.to_datetime(features_df["timestamp"], utc=True, errors="coerce")
        if ts.isna().any():
            raise ValueError("strategy_timestamp_invalid")
        return features_df.loc[ts <= as_of_ts]

    if isinstance(features_df.index, pd.DatetimeIndex):
        ts = pd.to_datetime(features_df.index, utc=True, errors="coerce")
        if ts.isna().any():
            raise ValueError("strategy_timestamp_invalid")
        return features_df.loc[ts <= as_of_ts]

    return features_df


def trend_follow_v1_runner(
    features_df: pd.DataFrame,
    metadata: Mapping[str, Any] | Any,
    as_of_utc: str,
) -> Decision:
    if not isinstance(features_df, pd.DataFrame):
        raise ValueError("strategy_features_invalid")
    if not isinstance(as_of_utc, str) or not as_of_utc:
        raise ValueError("strategy_as_of_invalid")

    filtered = _filter_to_as_of(features_df, as_of_utc)
    _validate_required_columns(filtered)
    indicators = _load_indicators(filtered)
    latest = _latest_two_rows(indicators)
    action, signals = _decision_action(latest)
    risk, entry_price = _risk_fields(latest.iloc[1])

    provenance = DecisionProvenance(
        feature_bundle_fingerprint=_bundle_fingerprint(metadata),
        strategy_id=f"{TREND_FOLLOW_V1_SPEC.name}@{TREND_FOLLOW_V1_SPEC.version}",
        strategy_params_hash=params_hash(TREND_FOLLOW_V1_SPEC.params),
    )

    return Decision(
        schema_version=DECISION_SCHEMA_VERSION,
        as_of_utc=as_of_utc,
        instrument=_instrument(features_df, metadata),
        action=action,
        rationale=_rationale(latest, signals, entry_price),
        risk=risk,
        provenance=provenance,
    )


__all__ = ["TREND_FOLLOW_V1_SPEC", "trend_follow_v1_runner", "_compute_indicators_from_ohlcv"]

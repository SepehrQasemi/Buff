"""Deterministic feature construction for M3 market state inputs."""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

from buff.features.indicators import adx_wilder, atr_wilder, ema, rsi_slope, rsi_wilder

REQUIRED_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]

LOG_RETURN_WINDOWS = (1, 5, 20)
VOLUME_ZSCORE_WINDOW = 20
EMA_FAST = 20
EMA_SLOW = 50
RSI_PERIOD = 14
RSI_SLOPE_PERIOD = 5
ATR_PERIOD = 14
REALIZED_VOL_WINDOW = 20
ADX_PERIOD = 14
FEATURE_COLUMNS = [
    "log_return_1",
    "log_return_5",
    "log_return_20",
    "volume_zscore_20",
    "ema_20",
    "ema_50",
    "ema_spread_20_50_pct",
    "rsi_14",
    "rsi_slope_14_5",
    "atr_14",
    "atr_pct",
    "realized_vol_20",
    "adx_14",
]


def _ensure_columns(df: pd.DataFrame, required: Iterable[str]) -> None:
    missing = sorted(set(required) - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def _normalize_timestamp(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        ts = pd.to_datetime(series, unit="ms", utc=True, errors="coerce")
    else:
        ts = pd.to_datetime(series, utc=True, errors="coerce")
    if ts.isna().any():
        raise ValueError("Invalid timestamp values")
    return ts


def _prepare_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    _ensure_columns(df, REQUIRED_COLUMNS)
    if df.empty:
        empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"], dtype="float64")
        empty.index = pd.DatetimeIndex([], name="timestamp")
        return empty

    data = df.copy()
    data["timestamp"] = _normalize_timestamp(data["timestamp"])

    if data["timestamp"].duplicated().any():
        raise ValueError("Duplicate timestamps are not allowed")
    if not data["timestamp"].is_monotonic_increasing:
        raise ValueError("Timestamps must be monotonic increasing")

    for col in ["open", "high", "low", "close", "volume"]:
        numeric = pd.to_numeric(data[col], errors="coerce")
        if numeric.isna().any():
            raise ValueError(f"Non-numeric or NaN values found in '{col}'")
        data[col] = numeric.astype("float64")

    data = data.sort_values("timestamp")
    data.index = data["timestamp"]
    data.index.name = "timestamp"
    return data.drop(columns=["timestamp"])


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute deterministic features using only past and current bars."""
    ohlcv = _prepare_ohlcv(df)
    if ohlcv.empty:
        return pd.DataFrame(columns=FEATURE_COLUMNS, index=ohlcv.index)

    close = ohlcv["close"]
    high = ohlcv["high"]
    low = ohlcv["low"]
    volume = ohlcv["volume"]

    # Past-only log returns via positive shifts.
    log_return_1 = np.log(close / close.shift(LOG_RETURN_WINDOWS[0]))
    log_return_5 = np.log(close / close.shift(LOG_RETURN_WINDOWS[1]))
    log_return_20 = np.log(close / close.shift(LOG_RETURN_WINDOWS[2]))

    # Rolling windows are explicitly past/current only (no centering).
    vol_mean = volume.rolling(window=VOLUME_ZSCORE_WINDOW, min_periods=VOLUME_ZSCORE_WINDOW).mean()
    vol_std = volume.rolling(window=VOLUME_ZSCORE_WINDOW, min_periods=VOLUME_ZSCORE_WINDOW).std(
        ddof=0
    )
    volume_zscore_20 = (volume - vol_mean) / vol_std.replace(0.0, np.nan)

    ema_20 = ema(close, period=EMA_FAST)
    ema_50 = ema(close, period=EMA_SLOW)
    ema_spread_20_50_pct = (ema_20 - ema_50) / ema_50.replace(0.0, np.nan)

    rsi_14 = rsi_wilder(close, period=RSI_PERIOD)
    rsi_slope_14_5 = rsi_slope(close, period=RSI_PERIOD, slope=RSI_SLOPE_PERIOD)

    atr_14 = atr_wilder(high, low, close, period=ATR_PERIOD)
    atr_pct = atr_14 / close.replace(0.0, np.nan)

    # Realized volatility uses a fixed past window of log returns.
    realized_vol_20 = log_return_1.rolling(
        window=REALIZED_VOL_WINDOW, min_periods=REALIZED_VOL_WINDOW
    ).std(ddof=0)

    adx_14_frame = adx_wilder(high, low, close, period=ADX_PERIOD)
    adx_14 = adx_14_frame["adx"]

    out = pd.DataFrame(
        {
            "log_return_1": log_return_1,
            "log_return_5": log_return_5,
            "log_return_20": log_return_20,
            "volume_zscore_20": volume_zscore_20,
            "ema_20": ema_20,
            "ema_50": ema_50,
            "ema_spread_20_50_pct": ema_spread_20_50_pct,
            "rsi_14": rsi_14,
            "rsi_slope_14_5": rsi_slope_14_5,
            "atr_14": atr_14,
            "atr_pct": atr_pct,
            "realized_vol_20": realized_vol_20,
            "adx_14": adx_14,
        },
        index=ohlcv.index,
    )
    out = out[FEATURE_COLUMNS]
    out.index.name = "timestamp"
    return out

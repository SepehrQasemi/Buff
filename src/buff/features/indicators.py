"""Minimal indicator implementations for M3-min."""

from __future__ import annotations

import pandas as pd


def ema(close: pd.Series, period: int = 20) -> pd.Series:
    if period <= 0:
        raise ValueError("period must be > 0")

    close = close.astype(float)
    return close.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    if period <= 0:
        raise ValueError("period must be > 0")

    close = close.astype(float)
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    if len(gain):
        gain.iloc[0] = 0.0
        loss.iloc[0] = 0.0
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.mask(avg_loss == 0, 100.0)
    return rsi


def atr_wilder(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    if period <= 0:
        raise ValueError("period must be > 0")

    high = high.astype(float)
    low = low.astype(float)
    close = close.astype(float)

    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    out = pd.Series(0.0, index=close.index, dtype=float)
    if len(tr) < period:
        return out

    atr = tr.iloc[:period].mean()
    out.iloc[period - 1] = atr

    for i in range(period, len(tr)):
        atr = ((atr * (period - 1)) + tr.iloc[i]) / period
        out.iloc[i] = atr

    return out

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


def sma(close: pd.Series, period: int = 20) -> pd.Series:
    if period <= 0:
        raise ValueError("period must be > 0")

    close = close.astype(float)
    return close.rolling(window=period, min_periods=period).mean()


def rolling_std(close: pd.Series, period: int = 20, ddof: int = 0) -> pd.Series:
    if period <= 0:
        raise ValueError("period must be > 0")

    close = close.astype(float)
    return close.rolling(window=period, min_periods=period).std(ddof=ddof)


def bollinger_bands(
    close: pd.Series,
    period: int = 20,
    k: float = 2.0,
    ddof: int = 0,
) -> pd.DataFrame:
    mid = sma(close, period=period)
    sd = rolling_std(close, period=period, ddof=ddof)
    upper = mid + (k * sd)
    lower = mid - (k * sd)
    return pd.DataFrame({"mid": mid, "upper": upper, "lower": lower})


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    if fast <= 0 or slow <= 0 or signal <= 0:
        raise ValueError("fast, slow, and signal must be > 0")
    if fast >= slow:
        raise ValueError("fast must be < slow")

    macd_line = ema(close, period=fast) - ema(close, period=slow)
    signal_line = ema(macd_line, period=signal)
    hist = macd_line - signal_line

    warmup = slow + signal - 1
    if len(macd_line) >= warmup:
        macd_line.iloc[: warmup - 1] = float("nan")
        signal_line.iloc[: warmup - 1] = float("nan")
        hist.iloc[: warmup - 1] = float("nan")
    else:
        macd_line[:] = float("nan")
        signal_line[:] = float("nan")
        hist[:] = float("nan")

    return pd.DataFrame(
        {
            "macd": macd_line,
            "signal": signal_line,
            "hist": hist,
        }
    )

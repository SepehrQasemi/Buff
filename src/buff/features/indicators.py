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


def adx_wilder(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.DataFrame:
    if period <= 0:
        raise ValueError("period must be > 0")

    high = high.astype(float)
    low = low.astype(float)
    close = close.astype(float)

    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = close.shift(1)

    up_move = high - prev_high
    down_move = prev_low - low

    plus_dm = pd.Series(0.0, index=high.index, dtype=float)
    minus_dm = pd.Series(0.0, index=high.index, dtype=float)
    plus_dm = plus_dm.mask((up_move > down_move) & (up_move > 0), up_move)
    minus_dm = minus_dm.mask((down_move > up_move) & (down_move > 0), down_move)
    plus_dm = plus_dm.fillna(0.0)
    minus_dm = minus_dm.fillna(0.0)

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    out = pd.DataFrame(
        {
            "plus_di": pd.Series(float("nan"), index=high.index, dtype=float),
            "minus_di": pd.Series(float("nan"), index=high.index, dtype=float),
            "adx": pd.Series(float("nan"), index=high.index, dtype=float),
        }
    )

    if len(tr) <= period:
        return out

    tr.iloc[0] = 0.0
    plus_dm.iloc[0] = 0.0
    minus_dm.iloc[0] = 0.0

    tr_smooth = tr.iloc[1 : period + 1].sum()
    plus_dm_smooth = plus_dm.iloc[1 : period + 1].sum()
    minus_dm_smooth = minus_dm.iloc[1 : period + 1].sum()

    def _di(dm_val: float, tr_val: float) -> float:
        if tr_val == 0.0:
            return 0.0
        return 100.0 * (dm_val / tr_val)

    di_index = period
    plus_di = _di(plus_dm_smooth, tr_smooth)
    minus_di = _di(minus_dm_smooth, tr_smooth)
    out.iloc[di_index, out.columns.get_loc("plus_di")] = plus_di
    out.iloc[di_index, out.columns.get_loc("minus_di")] = minus_di
    dx_values: list[float] = []
    denom = plus_di + minus_di
    dx_values.append(0.0 if denom == 0.0 else 100.0 * abs(plus_di - minus_di) / denom)

    for i in range(period + 1, len(tr)):
        tr_smooth = tr_smooth - (tr_smooth / period) + tr.iloc[i]
        plus_dm_smooth = plus_dm_smooth - (plus_dm_smooth / period) + plus_dm.iloc[i]
        minus_dm_smooth = minus_dm_smooth - (minus_dm_smooth / period) + minus_dm.iloc[i]

        plus_di = _di(plus_dm_smooth, tr_smooth)
        minus_di = _di(minus_dm_smooth, tr_smooth)
        out.iloc[i, out.columns.get_loc("plus_di")] = plus_di
        out.iloc[i, out.columns.get_loc("minus_di")] = minus_di

        denom = plus_di + minus_di
        dx_values.append(0.0 if denom == 0.0 else 100.0 * abs(plus_di - minus_di) / denom)

    if len(dx_values) < period:
        return out

    adx_start = period * 2
    if adx_start < len(tr):
        adx = sum(dx_values[:period]) / period
        out.iloc[adx_start, out.columns.get_loc("adx")] = adx
        dx_idx = period
        for i in range(adx_start + 1, len(tr)):
            dx_idx += 1
            adx = ((adx * (period - 1)) + dx_values[dx_idx]) / period
            out.iloc[i, out.columns.get_loc("adx")] = adx

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


def roc(close: pd.Series, period: int = 12) -> pd.Series:
    if period <= 0:
        raise ValueError("period must be > 0")

    close = close.astype(float)
    return 100.0 * (close / close.shift(period) - 1.0)


def vwap_typical_daily(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series
) -> pd.Series:
    high = high.astype(float)
    low = low.astype(float)
    close = close.astype(float)
    volume = volume.astype(float)

    if isinstance(high.index, pd.DatetimeIndex):
        dates = pd.Series(high.index.normalize(), index=high.index)
    else:
        dates = pd.Series(range(len(high)), index=high.index)

    typical = (high + low + close) / 3.0
    pv = typical * volume
    out = pd.Series(float("nan"), index=high.index, dtype=float)

    for _, idx in dates.groupby(dates).groups.items():
        day_idx = pd.Index(idx)
        day_pv = pv.loc[day_idx].cumsum()
        day_v = volume.loc[day_idx].cumsum()
        out.loc[day_idx] = day_pv / day_v.replace(0.0, float("nan"))

    return out


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    close = close.astype(float)
    volume = volume.astype(float)

    delta = close.diff()
    direction = delta.apply(lambda x: 1.0 if x > 0 else (-1.0 if x < 0 else 0.0))
    direction.iloc[0] = 0.0
    return (volume * direction).cumsum()


def ema_spread(close: pd.Series, fast: int = 20, slow: int = 50) -> pd.Series:
    if fast <= 0 or slow <= 0:
        raise ValueError("fast and slow must be > 0")
    if fast >= slow:
        raise ValueError("fast must be < slow")
    return ema(close, period=fast) - ema(close, period=slow)


def rsi_slope(close: pd.Series, period: int = 14, slope: int = 5) -> pd.Series:
    if slope <= 0:
        raise ValueError("slope must be > 0")
    rsi = rsi_wilder(close, period=period)
    return (rsi - rsi.shift(slope)) / float(slope)

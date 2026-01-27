"""Deterministic OHLCV resampling from 1m base timeframe."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


FIXED_TIMEFRAMES_MINUTES = {
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "4h": 240,
    "1d": 1440,
    "1w": 10080,
    "2w": 20160,
}

CALENDAR_TIMEFRAMES = {
    "1M": {"rule": "MS", "months": 1},
    "3M": {"rule": "QS-JAN", "months": 3},
    "6M": {"rule": "2QS-JAN", "months": 6},
    "1Y": {"rule": "YS", "years": 1},
}


@dataclass(frozen=True)
class ResampleResult:
    """Resampled dataframe and dropped last-window flag."""

    df: pd.DataFrame
    dropped_last: bool


def _aggregate_ohlcv(resampled: pd.core.resample.Resampler) -> pd.DataFrame:
    ohlcv = resampled.agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    return ohlcv


def _drop_empty(df: pd.DataFrame) -> pd.DataFrame:
    return df.dropna(subset=["open", "high", "low", "close", "volume"])


def resample_fixed(df: pd.DataFrame, timeframe: str) -> ResampleResult:
    """Resample 1m OHLCV into fixed-duration timeframe."""
    if timeframe not in FIXED_TIMEFRAMES_MINUTES:
        raise ValueError(f"Unknown fixed timeframe: {timeframe}")

    if df.empty:
        return ResampleResult(df.copy(), dropped_last=False)

    minutes = FIXED_TIMEFRAMES_MINUTES[timeframe]
    if timeframe == "1w":
        rule = "W-MON"
    elif timeframe == "2w":
        rule = "2W-MON"
    elif minutes < 60:
        rule = f"{minutes}T"
    elif minutes % 60 == 0:
        rule = f"{minutes // 60}H"
    else:
        rule = f"{minutes}T"

    frame = df.sort_values("ts").set_index("ts")
    resampled = frame.resample(rule, label="left", closed="left")
    ohlcv = _aggregate_ohlcv(resampled)
    counts = resampled["open"].count()

    ohlcv = _drop_empty(ohlcv)
    counts = counts.loc[ohlcv.index]

    dropped_last = False
    if not ohlcv.empty:
        last_idx = ohlcv.index[-1]
        if counts.loc[last_idx] < minutes:
            ohlcv = ohlcv.iloc[:-1]
            dropped_last = True

    ohlcv = ohlcv.reset_index().rename(columns={"index": "ts"})
    return ResampleResult(ohlcv.reset_index(drop=True), dropped_last=dropped_last)


def resample_calendar(df: pd.DataFrame, timeframe: str) -> ResampleResult:
    """Resample 1m OHLCV into calendar-based timeframe."""
    if timeframe not in CALENDAR_TIMEFRAMES:
        raise ValueError(f"Unknown calendar timeframe: {timeframe}")

    if df.empty:
        return ResampleResult(df.copy(), dropped_last=False)

    rule = CALENDAR_TIMEFRAMES[timeframe]["rule"]
    frame = df.sort_values("ts").set_index("ts")
    resampled = frame.resample(rule, label="left", closed="left")
    ohlcv = _aggregate_ohlcv(resampled)
    max_ts = resampled["open"].apply(lambda x: x.index.max() if len(x) else pd.NaT)

    ohlcv = _drop_empty(ohlcv)
    max_ts = max_ts.loc[ohlcv.index]

    dropped_last = False
    if not ohlcv.empty:
        last_start = ohlcv.index[-1]
        last_max = max_ts.loc[last_start]
        if pd.isna(last_max):
            ohlcv = ohlcv.iloc[:-1]
            dropped_last = True
        else:
            if timeframe == "1M":
                bucket_end = last_start + pd.DateOffset(months=1)
            elif timeframe == "3M":
                bucket_end = last_start + pd.DateOffset(months=3)
            elif timeframe == "6M":
                bucket_end = last_start + pd.DateOffset(months=6)
            elif timeframe == "1Y":
                bucket_end = last_start + pd.DateOffset(years=1)
            else:
                raise ValueError(f"Unknown calendar timeframe: {timeframe}")

            if last_max < (bucket_end - pd.Timedelta(minutes=1)):
                ohlcv = ohlcv.iloc[:-1]
                dropped_last = True

    ohlcv = ohlcv.reset_index().rename(columns={"index": "ts"})
    return ResampleResult(ohlcv.reset_index(drop=True), dropped_last=dropped_last)


def resample_ohlcv(df: pd.DataFrame, timeframe: str) -> ResampleResult:
    """Resample OHLCV 1m data into requested timeframe."""
    if timeframe in FIXED_TIMEFRAMES_MINUTES:
        return resample_fixed(df, timeframe)
    if timeframe in CALENDAR_TIMEFRAMES:
        return resample_calendar(df, timeframe)
    if timeframe == "1m":
        return ResampleResult(df.sort_values("ts").reset_index(drop=True), dropped_last=False)
    raise ValueError(f"Unsupported timeframe: {timeframe}")


def split_timeframes(timeframes: Iterable[str]) -> tuple[list[str], list[str]]:
    fixed = [tf for tf in timeframes if tf in FIXED_TIMEFRAMES_MINUTES]
    calendar = [tf for tf in timeframes if tf in CALENDAR_TIMEFRAMES]
    return fixed, calendar

"""Timeframe registry for shared definitions."""

BASE_TIMEFRAME = "1m"

DERIVED_TIMEFRAMES = [
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "1d",
    "1w",
    "2w",
    "1M",
    "3M",
    "6M",
    "1Y",
]

ALL_TIMEFRAMES = [BASE_TIMEFRAME] + DERIVED_TIMEFRAMES

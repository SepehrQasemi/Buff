"""Feature registry for deterministic feature computation."""

from __future__ import annotations

from buff.features.indicators import atr_wilder, ema, rsi_wilder


FEATURES = {
    "ema_20": {
        "callable": lambda df: ema(df["close"], period=20),
        "required_columns": ["close"],
    },
    "rsi_14": {
        "callable": lambda df: rsi_wilder(df["close"], period=14),
        "required_columns": ["close"],
    },
    "atr_14": {
        "callable": lambda df: atr_wilder(df["high"], df["low"], df["close"], period=14),
        "required_columns": ["high", "low", "close"],
    },
}

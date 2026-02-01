"""Feature registry for deterministic feature computation."""

from __future__ import annotations

from buff.features.indicators import (
    adx_wilder,
    atr_wilder,
    bollinger_bands,
    ema,
    ema_spread,
    macd,
    obv,
    roc,
    rolling_std,
    rsi_wilder,
    rsi_slope,
    sma,
    vwap_typical_daily,
)


FEATURES = {
    "ema_20": {
        "requires": ["close"],
        "kind": "ema",
        "func": lambda df, **params: ema(df["close"], **params),
        "params": {"period": 20},
        "outputs": ["ema_20"],
    },
    "rsi_14": {
        "requires": ["close"],
        "kind": "rsi",
        "func": lambda df, **params: rsi_wilder(df["close"], **params),
        "params": {"period": 14},
        "outputs": ["rsi_14"],
    },
    "atr_14": {
        "requires": ["high", "low", "close"],
        "kind": "atr",
        "func": lambda df, **params: atr_wilder(df["high"], df["low"], df["close"], **params),
        "params": {"period": 14},
        "outputs": ["atr_14"],
    },
    "sma_20": {
        "requires": ["close"],
        "kind": "sma",
        "func": lambda df, **params: sma(df["close"], **params),
        "params": {"period": 20},
        "outputs": ["sma_20"],
    },
    "std_20": {
        "requires": ["close"],
        "kind": "std",
        "func": lambda df, **params: rolling_std(df["close"], **params),
        "params": {"period": 20, "ddof": 0},
        "outputs": ["std_20"],
    },
    "bbands_20_2": {
        "requires": ["close"],
        "kind": "bbands",
        "func": lambda df, **params: bollinger_bands(df["close"], **params),
        "params": {"period": 20, "k": 2.0, "ddof": 0},
        "outputs": ["bb_mid_20_2", "bb_upper_20_2", "bb_lower_20_2"],
    },
    "macd_12_26_9": {
        "requires": ["close"],
        "kind": "macd",
        "func": lambda df, **params: macd(df["close"], **params),
        "params": {"fast": 12, "slow": 26, "signal": 9},
        "outputs": ["macd_12_26_9", "macd_signal_12_26_9", "macd_hist_12_26_9"],
    },
    "ema_50": {
        "requires": ["close"],
        "kind": "ema",
        "func": lambda df, **params: ema(df["close"], **params),
        "params": {"period": 50},
        "outputs": ["ema_50"],
    },
    "ema_spread_20_50": {
        "requires": ["close"],
        "kind": "ema_spread",
        "func": lambda df, **params: ema_spread(df["close"], **params),
        "params": {"fast": 20, "slow": 50},
        "outputs": ["ema_spread_20_50"],
    },
    "rsi_slope_14_5": {
        "requires": ["close"],
        "kind": "rsi_slope",
        "func": lambda df, **params: rsi_slope(df["close"], **params),
        "params": {"period": 14, "slope": 5},
        "outputs": ["rsi_slope_14_5"],
    },
    "roc_12": {
        "requires": ["close"],
        "kind": "roc",
        "func": lambda df, **params: roc(df["close"], **params),
        "params": {"period": 12},
        "outputs": ["roc_12"],
    },
    "vwap_typical_daily": {
        "requires": ["high", "low", "close", "volume"],
        "kind": "vwap",
        "func": lambda df, **params: vwap_typical_daily(
            df["high"], df["low"], df["close"], df["volume"], **params
        ),
        "params": {},
        "outputs": ["vwap_typical_daily"],
    },
    "obv": {
        "requires": ["close", "volume"],
        "kind": "obv",
        "func": lambda df, **params: obv(df["close"], df["volume"], **params),
        "params": {},
        "outputs": ["obv"],
    },
    "adx_14": {
        "requires": ["high", "low", "close"],
        "kind": "adx",
        "func": lambda df, **params: adx_wilder(df["high"], df["low"], df["close"], **params),
        "params": {"period": 14},
        "outputs": ["plus_di_14", "minus_di_14", "adx_14"],
    },
}

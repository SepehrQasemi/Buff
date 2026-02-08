from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

from strategies.builtins.common import StrategyContext


def synthetic_ohlcv(num_bars: int = 200) -> pd.DataFrame:
    idx = pd.RangeIndex(num_bars)
    base = np.linspace(100.0, 120.0, num_bars)
    wave = np.sin(np.linspace(0, 6 * np.pi, num_bars)) * 3.0
    close = base + wave
    open_ = close + np.cos(np.linspace(0, 6 * np.pi, num_bars)) * 0.5
    high = np.maximum(open_, close) + 1.0
    low = np.minimum(open_, close) - 1.0
    volume = np.linspace(1000.0, 1200.0, num_bars)
    df = pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=idx,
    )
    return df


def run_intents(
    strategy,
    ohlcv: pd.DataFrame,
    *,
    params: Mapping[str, Any] | None = None,
) -> list[str]:
    intents: list[str] = []
    for idx in range(len(ohlcv)):
        history = ohlcv.iloc[: idx + 1]
        ctx = StrategyContext(history=history, params=params or {})
        result = strategy.on_bar(ctx)
        intents.append(str(result.get("intent")))
    return intents

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

from strategies.builtins.common import PositionState, StrategyContext, zscore_series
from strategies.builtins.mean_reversion import zscore_reversion_on_bar


def _zscore_for(close: Iterable[float], lookback: int) -> float:
    series = pd.Series(close, dtype=float)
    value = zscore_series(series, period=lookback).iloc[-1]
    return float(value)


def _solve_last_value(
    *,
    base: list[float],
    lookback: int,
    target_z: float,
) -> float:
    low = min(base) - 50.0
    high = max(base) + 50.0

    for _ in range(80):
        mid = (low + high) / 2.0
        z = _zscore_for(base + [mid], lookback)
        if z < target_z:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def _make_history(close: list[float]) -> pd.DataFrame:
    arr = np.array(close, dtype=float)
    return pd.DataFrame(
        {
            "open": arr,
            "high": arr + 1.0,
            "low": arr - 1.0,
            "close": arr,
            "volume": np.full_like(arr, 1000.0),
        }
    )


def test_zscore_reversion_exit_respects_position_side() -> None:
    lookback = 20
    exit_z = 0.5
    base = list(np.linspace(100.0, 118.0, lookback - 1))

    last_short = _solve_last_value(base=base, lookback=lookback, target_z=0.4)
    close_short = base + [last_short]
    z_short = _zscore_for(close_short, lookback)
    assert z_short <= exit_z

    short_pos = PositionState(
        side="SHORT",
        entry_price=close_short[-2],
        entry_index=len(close_short) - 2,
        max_price=max(close_short),
        min_price=min(close_short),
        bars_in_trade=5,
    )
    ctx_short = StrategyContext(
        history=_make_history(close_short),
        params={"lookback": lookback, "entry_z": 2.0, "exit_z": exit_z},
        position=short_pos,
    )
    result_short = zscore_reversion_on_bar(ctx_short)
    assert result_short["intent"] == "EXIT_SHORT"
    assert result_short["intent"] != "EXIT_LONG"

    last_long = _solve_last_value(base=base, lookback=lookback, target_z=-0.4)
    close_long = base + [last_long]
    z_long = _zscore_for(close_long, lookback)
    assert z_long >= -exit_z

    long_pos = PositionState(
        side="LONG",
        entry_price=close_long[-2],
        entry_index=len(close_long) - 2,
        max_price=max(close_long),
        min_price=min(close_long),
        bars_in_trade=5,
    )
    ctx_long = StrategyContext(
        history=_make_history(close_long),
        params={"lookback": lookback, "entry_z": 2.0, "exit_z": exit_z},
        position=long_pos,
    )
    result_long = zscore_reversion_on_bar(ctx_long)
    assert result_long["intent"] == "EXIT_LONG"
    assert result_long["intent"] != "EXIT_SHORT"

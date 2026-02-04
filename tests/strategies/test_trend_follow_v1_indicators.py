from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from buff.features.indicators import atr_wilder, ema, rsi_wilder
from strategies.runners.trend_follow_v1 import _compute_indicators_from_ohlcv


def test_indicator_calcs_match_reference() -> None:
    rows = 60
    close = pd.Series(np.linspace(100.0, 110.0, rows))
    high = close + 1.0
    low = close - 1.0
    df = pd.DataFrame({"close": close, "high": high, "low": low})

    computed = _compute_indicators_from_ohlcv(df)

    ema_20_ref = ema(close, period=20).iloc[-1]
    ema_50_ref = ema(close, period=50).iloc[-1]
    rsi_14_ref = rsi_wilder(close, period=14).iloc[-1]
    atr_14_ref = atr_wilder(high, low, close, period=14).iloc[-1]

    assert computed["ema_20"].iloc[-1] == pytest.approx(ema_20_ref, rel=1e-9)
    assert computed["ema_50"].iloc[-1] == pytest.approx(ema_50_ref, rel=1e-9)
    assert computed["rsi_14"].iloc[-1] == pytest.approx(rsi_14_ref, rel=1e-9)
    assert computed["atr_14"].iloc[-1] == pytest.approx(atr_14_ref, rel=1e-9)

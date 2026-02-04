from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from buff.features.indicators import bollinger_bands
from strategies.runners.mean_revert_v1 import _compute_indicators_from_ohlcv


def test_bollinger_bands_match_reference() -> None:
    rows = 60
    close = pd.Series(np.linspace(100.0, 120.0, rows))
    high = close + 1.0
    low = close - 1.0
    df = pd.DataFrame({"close": close, "high": high, "low": low})

    computed = _compute_indicators_from_ohlcv(df)
    reference = bollinger_bands(close, period=20, k=2.0, ddof=0)

    assert computed["bb_mid_20_2"].iloc[-1] == pytest.approx(reference["mid"].iloc[-1], rel=1e-9)
    assert computed["bb_upper_20_2"].iloc[-1] == pytest.approx(
        reference["upper"].iloc[-1], rel=1e-9
    )
    assert computed["bb_lower_20_2"].iloc[-1] == pytest.approx(
        reference["lower"].iloc[-1], rel=1e-9
    )

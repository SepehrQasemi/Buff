from __future__ import annotations

import numpy as np
import pandas as pd


def make_ohlcv(rows: int = 200, start: str = "2024-01-01T00:00:00Z") -> pd.DataFrame:
    base = pd.Timestamp(start)
    idx = np.arange(rows, dtype=float)
    timestamps = [int((base + pd.Timedelta(hours=i)).timestamp() * 1000) for i in range(rows)]

    trend = 0.05 * idx
    seasonal = 2.0 * np.sin(idx / 12.0)
    close = 100.0 + trend + seasonal
    open_ = close + 0.1 * np.cos(idx / 8.0)
    high = np.maximum(open_, close) + 0.5
    low = np.minimum(open_, close) - 0.5
    volume = 1000.0 + 25.0 * (idx % 5)

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )

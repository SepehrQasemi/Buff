from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtest.harness import run_backtest


def _make_ohlcv() -> pd.DataFrame:
    idx = pd.date_range("2026-02-01", periods=81, freq="min", tz="UTC")
    close = np.array([100.0] * 79 + [98.5, 100.0])
    open_ = close.copy()
    open_[-1] = 99.0
    high = close + 1.0
    low = close - 1.0
    low[-1] = 90.0
    volume = np.ones_like(close) * 1000.0
    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )
    df.index.name = "timestamp"
    return df


def test_golden(tmp_path: Path) -> None:
    df = _make_ohlcv()
    result = run_backtest(df, 10_000.0, run_id="golden", out_dir=tmp_path)

    assert result.trades_path.exists()
    assert result.metrics_path.exists()
    assert result.decision_records_path.exists()
    assert result.manifest_path.exists()

    trades = result.trades
    assert len(trades) == 2
    assert trades.iloc[0]["side"] == "BUY"
    assert trades.iloc[1]["side"] == "SELL"
    assert trades.iloc[0]["price"] == pytest.approx(99.0, rel=1e-9)

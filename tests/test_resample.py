"""Unit tests for 1m-based resampling."""

import pandas as pd
import pytest

from buff.data.report import build_report
from buff.data.resample import resample_ohlcv
from buff.data.store import ohlcv_parquet_path, save_parquet


pytestmark = pytest.mark.unit


def test_resample_fixed_5m_correctness() -> None:
    dates = pd.date_range("2023-01-01", periods=10, freq="1min", tz="UTC")
    df = pd.DataFrame({
        "ts": dates,
        "open": list(range(10)),
        "high": [i + 1 for i in range(10)],
        "low": [i - 1 for i in range(10)],
        "close": [i + 0.5 for i in range(10)],
        "volume": [1.0] * 10,
    })

    res = resample_ohlcv(df, "5m").df

    assert len(res) == 2
    first = res.iloc[0]
    second = res.iloc[1]

    assert first["open"] == 0
    assert first["high"] == 5
    assert first["low"] == -1
    assert first["close"] == 4.5
    assert first["volume"] == 5.0

    assert second["open"] == 5
    assert second["high"] == 10
    assert second["low"] == 4
    assert second["close"] == 9.5
    assert second["volume"] == 5.0


def test_resample_fixed_1h_correctness() -> None:
    dates = pd.date_range("2023-01-01", periods=60, freq="1min", tz="UTC")
    df = pd.DataFrame({
        "ts": dates,
        "open": list(range(60)),
        "high": [i + 1 for i in range(60)],
        "low": [i - 1 for i in range(60)],
        "close": [i + 0.5 for i in range(60)],
        "volume": [1.0] * 60,
    })

    res = resample_ohlcv(df, "1h").df

    assert len(res) == 1
    row = res.iloc[0]
    assert row["open"] == 0
    assert row["high"] == 60
    assert row["low"] == -1
    assert row["close"] == 59.5
    assert row["volume"] == 60.0


def test_resample_determinism() -> None:
    dates = pd.date_range("2023-01-01", periods=12, freq="1min", tz="UTC")
    df = pd.DataFrame({
        "ts": dates,
        "open": list(range(12)),
        "high": [i + 1 for i in range(12)],
        "low": [i - 1 for i in range(12)],
        "close": [i + 0.5 for i in range(12)],
        "volume": [1.0] * 12,
    })

    res1 = resample_ohlcv(df, "5m").df
    res2 = resample_ohlcv(df, "5m").df

    assert res1.equals(res2)


def test_resample_calendar_1m_month_boundary() -> None:
    dates = pd.to_datetime(
        [
            "2023-01-01 00:00:00+00:00",
            "2023-01-31 23:59:00+00:00",
            "2023-02-01 00:00:00+00:00",
            "2023-02-28 23:59:00+00:00",
        ]
    )
    df = pd.DataFrame({
        "ts": dates,
        "open": [100.0, 101.0, 200.0, 201.0],
        "high": [110.0, 111.0, 210.0, 211.0],
        "low": [90.0, 91.0, 190.0, 191.0],
        "close": [105.0, 106.0, 205.0, 206.0],
        "volume": [1.0, 2.0, 3.0, 4.0],
    })

    res = resample_ohlcv(df, "1M").df

    assert len(res) == 2
    assert res.iloc[0]["ts"].isoformat().startswith("2023-01-01")
    assert res.iloc[1]["ts"].isoformat().startswith("2023-02-01")
    assert res.iloc[0]["open"] == 100.0
    assert res.iloc[0]["close"] == 106.0
    assert res.iloc[1]["open"] == 200.0
    assert res.iloc[1]["close"] == 206.0


def test_gap_propagation_to_5m(tmp_path) -> None:
    dates = pd.date_range("2023-01-01", periods=15, freq="1min", tz="UTC")
    df = pd.DataFrame({
        "ts": dates,
        "open": list(range(15)),
        "high": [i + 1 for i in range(15)],
        "low": [i - 1 for i in range(15)],
        "close": [i + 0.5 for i in range(15)],
        "volume": [1.0] * 15,
    })

    df = df[(df["ts"] < dates[5]) | (df["ts"] >= dates[10])]
    res_5m = resample_ohlcv(df, "5m").df

    data_dir = tmp_path / "data" / "ohlcv"
    save_parquet(res_5m, str(ohlcv_parquet_path(data_dir, "BTC/USDT", "5m")))

    report = build_report(data_dir, ["BTC/USDT"], ["5m"], strict=False)
    entry = report["per_symbol"][0]
    assert entry["missing_bars_count"] == 1

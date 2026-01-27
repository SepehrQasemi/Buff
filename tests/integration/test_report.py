"""Integration tests for deterministic data quality reporting."""

from pathlib import Path

import json
import pandas as pd
import pytest

from buff.data.report import build_report, write_report
from buff.data.store import save_parquet, symbol_to_filename


pytestmark = pytest.mark.integration


def _write_symbol(data_dir: Path, symbol: str, timeframe: str, df: pd.DataFrame) -> None:
    filename = symbol_to_filename(symbol, timeframe)
    save_parquet(df, str(data_dir / filename))


def test_report_determinism(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    timeframe = "1h"
    dates = pd.date_range("2022-01-01", periods=3, freq="1h", tz="UTC")
    df = pd.DataFrame(
        {
            "ts": dates,
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.5, 101.5, 102.5],
            "volume": [1000.0, 1100.0, 1200.0],
        }
    )

    _write_symbol(data_dir, "BTC/USDT", timeframe, df)
    _write_symbol(data_dir, "ETH/USDT", timeframe, df)

    report1 = build_report(data_dir, ["BTC/USDT", "ETH/USDT"], timeframe)
    report2 = build_report(data_dir, ["BTC/USDT", "ETH/USDT"], timeframe)

    out1 = tmp_path / "report1.json"
    out2 = tmp_path / "report2.json"
    write_report(report1, out1)
    write_report(report2, out2)

    assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")
    assert json.loads(out1.read_text(encoding="utf-8")) == json.loads(
        out2.read_text(encoding="utf-8")
    )


def test_report_detects_duplicates(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    timeframe = "1h"

    dates = pd.date_range("2022-01-01", periods=3, freq="1h", tz="UTC")
    dates_with_dup = pd.DatetimeIndex(list(dates) + [dates[1]])
    df = pd.DataFrame(
        {
            "ts": dates_with_dup,
            "open": [100.0] * 4,
            "high": [101.0] * 4,
            "low": [99.0] * 4,
            "close": [100.5] * 4,
            "volume": [1000.0] * 4,
        }
    )

    _write_symbol(data_dir, "BTC/USDT", timeframe, df)
    report = build_report(data_dir, ["BTC/USDT"], timeframe, strict=False)
    assert report["per_symbol"][0]["duplicates_count"] == 1


def test_report_detects_gaps(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    timeframe = "1h"

    dates = pd.DatetimeIndex(
        [
            pd.Timestamp("2022-01-01 00:00", tz="UTC"),
            pd.Timestamp("2022-01-01 01:00", tz="UTC"),
            pd.Timestamp("2022-01-01 03:00", tz="UTC"),
        ]
    )
    df = pd.DataFrame(
        {
            "ts": dates,
            "open": [100.0, 101.0, 103.0],
            "high": [101.0, 102.0, 104.0],
            "low": [99.0, 100.0, 102.0],
            "close": [100.5, 101.5, 103.5],
            "volume": [1000.0, 1100.0, 1300.0],
        }
    )

    _write_symbol(data_dir, "BTC/USDT", timeframe, df)
    report = build_report(data_dir, ["BTC/USDT"], timeframe, strict=False)
    symbol_report = report["per_symbol"][0]

    assert symbol_report["missing_bars_count"] == 1
    assert symbol_report["gaps_count"] == 1
    assert symbol_report["gap_ranges"][0]["missing_bars"] == 1


def test_report_fails_on_invalid_prices(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    timeframe = "1h"

    dates = pd.date_range("2022-01-01", periods=2, freq="1h", tz="UTC")
    df = pd.DataFrame(
        {
            "ts": dates,
            "open": [100.0, -1.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
            "volume": [1000.0, 1100.0],
        }
    )

    _write_symbol(data_dir, "BTC/USDT", timeframe, df)
    with pytest.raises(ValueError):
        build_report(data_dir, ["BTC/USDT"], timeframe, strict=True)


def test_report_fails_on_nans(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    timeframe = "1h"

    dates = pd.date_range("2022-01-01", periods=2, freq="1h", tz="UTC")
    df = pd.DataFrame(
        {
            "ts": dates,
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
            "volume": [1000.0, float("nan")],
        }
    )

    _write_symbol(data_dir, "BTC/USDT", timeframe, df)
    with pytest.raises(ValueError):
        build_report(data_dir, ["BTC/USDT"], timeframe, strict=True)

"""End-to-end determinism test for M1 report generation."""

import json
from pathlib import Path

import pandas as pd
import pytest

from buff.data.report import build_report, write_report
from buff.data.resample import resample_ohlcv
from buff.data.store import ohlcv_parquet_path, save_parquet


pytestmark = pytest.mark.integration


def _load_fixture_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def test_report_determinism_with_fixtures(tmp_path: Path) -> None:
    fixtures_dir = Path("tests/fixtures/ohlcv")
    data_dir = tmp_path / "data" / "ohlcv"

    symbols = ["BTC/USDT", "ETH/USDT"]
    timeframes = ["1m", "5m"]

    for symbol in symbols:
        filename = symbol.replace("/", "_") + "_1m.csv"
        df = _load_fixture_csv(fixtures_dir / filename)
        save_parquet(df, str(ohlcv_parquet_path(data_dir, symbol, "1m")))
        resampled = resample_ohlcv(df, "5m").df
        save_parquet(resampled, str(ohlcv_parquet_path(data_dir, symbol, "5m")))

    report1 = build_report(data_dir, symbols, timeframes, strict=True)
    report2 = build_report(data_dir, symbols, timeframes, strict=True)

    out1 = tmp_path / "report1.json"
    out2 = tmp_path / "report2.json"
    write_report(report1, out1)
    write_report(report2, out2)

    text1 = out1.read_text(encoding="utf-8")
    text2 = out2.read_text(encoding="utf-8")

    assert text1 == text2
    json1 = json.loads(text1)
    json2 = json.loads(text2)
    assert json1 == json2

    sha1 = [item["sha256"] for item in json1["per_symbol"]]
    sha2 = [item["sha256"] for item in json2["per_symbol"]]
    assert sha1 == sha2
    assert json1["global"]["sha256"] == json2["global"]["sha256"]

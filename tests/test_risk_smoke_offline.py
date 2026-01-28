"""Offline smoke test for manual risk report generation."""

import json
from pathlib import Path

import pandas as pd
import pytest

from buff.data.store import ohlcv_parquet_path, save_parquet
from manual.run_manual import main as manual_main


pytestmark = pytest.mark.unit


def _write_fixture_parquet(tmp_path: Path) -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    fixture_path = repo_root / "tests" / "fixtures" / "ohlcv" / "BTC_USDT_1h.csv"
    df = pd.read_csv(fixture_path)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    data_dir = tmp_path / "data" / "ohlcv"
    parquet_path = ohlcv_parquet_path(data_dir, "BTC/USDT", "1h")
    save_parquet(df, str(parquet_path))
    return data_dir


def test_manual_smoke_offline_generates_report(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUFF_REPO_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    data_dir = _write_fixture_parquet(tmp_path)
    argv = [
        "run_manual",
        "--workspace",
        "smoke",
        "--symbol",
        "BTCUSDT",
        "--timeframe",
        "1h",
        "--from",
        "2023-01-01",
        "--to",
        "2023-01-03",
        "--data_dir",
        str(data_dir),
    ]
    monkeypatch.setattr("sys.argv", argv)
    manual_main()

    report_path = tmp_path / "workspaces" / "smoke" / "reports" / "risk_report.json"
    assert report_path.exists()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["risk_report_version"] == 1

    monkeypatch.setattr("sys.argv", argv)
    manual_main()
    payload_second = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload == payload_second

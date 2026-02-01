from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.data import cli as data_cli
from src.data import ingest as data_ingest

MS = 60_000


def _make_df(start_ms: int, minutes: int, symbol: str) -> pd.DataFrame:
    timestamps = [start_ms + i * MS for i in range(minutes)]
    open_prices = [100.0 + i for i in range(minutes)]
    close_prices = [100.5 + i for i in range(minutes)]
    high_prices = [max(o, c) + 0.5 for o, c in zip(open_prices, close_prices)]
    low_prices = [min(o, c) - 0.5 for o, c in zip(open_prices, close_prices)]
    volume = [1.0 for _ in range(minutes)]
    return pd.DataFrame(
        {
            "symbol": [symbol for _ in range(minutes)],
            "timestamp": timestamps,
            "open": open_prices,
            "high": high_prices,
            "low": low_prices,
            "close": close_prices,
            "volume": volume,
        }
    )


def test_cli_date_only_until_inclusive_affects_ingest(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_download(symbols, start_time, end_time, **kwargs):
        captured["symbols"] = list(symbols)
        captured["start_time"] = start_time
        captured["end_time"] = end_time
        return _make_df(start_time, 1, symbols[0])

    def fake_write_parquet(df, out_dir, symbol, timeframe):
        return Path(out_dir) / symbol / timeframe / "data.parquet"

    monkeypatch.setattr(data_cli, "download_ohlcv_1m", fake_download)
    monkeypatch.setattr(data_cli, "write_parquet", fake_write_parquet)

    args = argparse.Namespace(
        symbols=["BTCUSDT"],
        since="2022-01-01T23:59:00Z",
        until="2022-01-01",
        timeframes=["1m"],
        out=str(tmp_path / "out"),
        report=str(tmp_path / "report.json"),
        rate_limit_sleep=0.0,
        max_retries=1,
        timeout_seconds=1,
        fail_on_zero_volume=False,
    )

    data_cli._run_ingest(args)

    expected_start = int(datetime(2022, 1, 1, 23, 59, tzinfo=timezone.utc).timestamp() * 1000)
    expected_end = int(datetime(2022, 1, 2, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)

    assert captured["symbols"] == ["BTCUSDT"]
    assert captured["start_time"] == expected_start
    assert captured["end_time"] == expected_end


def test_ingest_end_time_ceiled_when_seconds(monkeypatch) -> None:
    captured: dict[str, int] = {}

    def fake_fetch(symbol, start_ms, end_ms, **kwargs):
        captured["start_ms"] = start_ms
        captured["end_ms"] = end_ms
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    monkeypatch.setattr(data_ingest, "fetch_klines_1m", fake_fetch)

    data_ingest.download_ohlcv_1m(
        ["BTCUSDT"],
        "2022-01-01T00:00:30Z",
        "2022-01-01T00:01:30Z",
    )

    expected_start = int(datetime(2022, 1, 1, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
    expected_end = int(datetime(2022, 1, 1, 0, 2, tzinfo=timezone.utc).timestamp() * 1000)

    assert captured["start_ms"] == expected_start
    assert captured["end_ms"] == expected_end

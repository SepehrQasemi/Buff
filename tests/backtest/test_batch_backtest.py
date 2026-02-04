from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtest.batch import run_batch_backtests


def _make_ohlcv(*, last_open: float) -> pd.DataFrame:
    idx = pd.date_range("2026-02-01", periods=81, freq="min", tz="UTC")
    close = np.array([100.0] * 79 + [98.5, 100.0])
    open_ = close.copy()
    open_[-1] = float(last_open)
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


def test_batch_backtest_golden_two_runs(tmp_path: Path) -> None:
    datasets = {
        "BBB": _make_ohlcv(last_open=101.0),
        "AAA": _make_ohlcv(last_open=99.0),
    }
    result = run_batch_backtests(
        datasets,
        out_dir=tmp_path,
        timeframe="1m",
        start_at_utc=None,
        end_at_utc=None,
        initial_equity=10_000.0,
        costs={"commission_bps": 0.0, "slippage_bps": 0.0},
        seed_run_id_prefix="golden",
    )

    run_a = tmp_path / "golden_AAA_1m"
    run_b = tmp_path / "golden_BBB_1m"
    assert run_a.exists()
    assert run_b.exists()

    assert result.batch_dir == tmp_path / "batch_golden"
    assert result.summary_csv_path.exists()
    assert result.summary_json_path.exists()
    assert result.index_json_path.exists()

    summary = pd.read_csv(result.summary_csv_path)
    expected_cols = {
        "symbol",
        "timeframe",
        "status",
        "run_id",
        "error",
        "total_return",
        "max_drawdown",
        "num_trades",
        "total_costs",
        "data_quality",
    }
    assert expected_cols.issubset(set(summary.columns))
    assert list(summary["symbol"]) == ["AAA", "BBB"]
    assert set(summary["status"]) == {"OK"}

    index_payload = json.loads(result.index_json_path.read_text(encoding="utf-8"))
    metrics_a = json.loads(
        Path(index_payload["runs"]["golden_AAA_1m"]["artifacts"]["metrics"]).read_text(
            encoding="utf-8"
        )
    )
    metrics_b = json.loads(
        Path(index_payload["runs"]["golden_BBB_1m"]["artifacts"]["metrics"]).read_text(
            encoding="utf-8"
        )
    )
    expected_mean = (metrics_a["total_return"] + metrics_b["total_return"]) / 2.0

    summary_json = json.loads(result.summary_json_path.read_text(encoding="utf-8"))
    assert summary_json["counts"] == {"failed": 0, "ok": 2, "total": 2}
    assert summary_json["aggregates"]["total_return"]["mean"] == pytest.approx(
        expected_mean, rel=1e-12
    )

    top = summary_json["top_worst"]["top"]
    assert len(top) == 2
    best = "golden_BBB_1m" if metrics_b["total_return"] > metrics_a["total_return"] else "golden_AAA_1m"
    assert top[0]["run_id"] == best


def test_batch_backtest_failed_dataset_does_not_stop(tmp_path: Path) -> None:
    good = _make_ohlcv(last_open=99.0)
    bad = good.drop(columns=["volume"])
    datasets = {"GOOD": good, "BAD": bad}
    result = run_batch_backtests(
        datasets,
        out_dir=tmp_path,
        timeframe="1m",
        start_at_utc=None,
        end_at_utc=None,
        initial_equity=10_000.0,
        costs={"commission_bps": 0.0, "slippage_bps": 0.0},
        seed_run_id_prefix="failcase",
    )

    assert (tmp_path / "failcase_GOOD_1m").exists()
    assert not (tmp_path / "failcase_BAD_1m").exists()

    summary = pd.read_csv(result.summary_csv_path)
    status = {row["symbol"]: row["status"] for row in summary.to_dict(orient="records")}
    assert status["GOOD"] == "OK"
    assert status["BAD"] == "FAILED"

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtest.batch import run_batch_backtests
from backtest.batch import _pair_id
from backtest.harness import BacktestResult


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


def _make_ohlcv_n(*, periods: int, last_open: float) -> pd.DataFrame:
    idx = pd.date_range("2026-02-01", periods=periods, freq="min", tz="UTC")
    close = np.array([100.0] * max(periods - 2, 0) + [98.5, 100.0])[:periods]
    open_ = close.copy()
    if periods:
        open_[-1] = float(last_open)
    high = close + 1.0
    low = close - 1.0
    if periods:
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
        "split_type",
        "segment",
        "pair_id",
        "window_index",
        "status",
        "run_id",
        "config_id",
        "config_json",
        "error",
        "timestamp_repaired",
        "timestamp_repaired_reason",
        "strategy_share_available",
        "strategy_share_error",
        "strategy_counts_json",
        "primary_strategy",
        "primary_strategy_share",
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
    assert summary_json["schema_version"] == "batch_summary_v2"
    assert isinstance(summary_json["summary_columns"], list)
    assert summary_json["counts"]["total"] == 2
    assert summary_json["counts"]["ok"] == 2
    assert summary_json["counts"]["failed"] == 0
    assert summary_json["counts"]["success_count"] == 2
    assert summary_json["counts"]["failed_count"] == 0
    assert summary_json["counts"]["repaired_count"] == 0
    assert summary_json["aggregates"]["total_return"]["mean"] == pytest.approx(
        expected_mean, rel=1e-12
    )
    assert isinstance(summary_json["overall_strategy_share"], dict)

    top = summary_json["top_worst"]["top"]
    assert len(top) == 2
    best = (
        "golden_BBB_1m"
        if metrics_b["total_return"] > metrics_a["total_return"]
        else "golden_AAA_1m"
    )
    assert top[0]["run_id"] == best

    index_json = json.loads(result.index_json_path.read_text(encoding="utf-8"))
    assert index_json["schema_version"] == "batch_index_v2"


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


def test_schema_version_present(tmp_path: Path) -> None:
    df = _make_ohlcv(last_open=99.0)
    result = run_batch_backtests(
        {"AAA": df},
        out_dir=tmp_path,
        timeframe="1m",
        start_at_utc=None,
        end_at_utc=None,
        initial_equity=10_000.0,
        costs={"commission_bps": 0.0, "slippage_bps": 0.0},
        seed_run_id_prefix="schema",
    )
    summary_json = json.loads(result.summary_json_path.read_text(encoding="utf-8"))
    assert summary_json["schema_version"] == "batch_summary_v2"
    assert isinstance(summary_json["summary_columns"], list)
    index_json = json.loads(result.index_json_path.read_text(encoding="utf-8"))
    assert index_json["schema_version"] == "batch_index_v2"


def test_strategy_usage_share_fields_populated(tmp_path: Path) -> None:
    datasets = {"AAA": _make_ohlcv(last_open=99.0)}
    result = run_batch_backtests(
        datasets,
        out_dir=tmp_path,
        timeframe="1m",
        start_at_utc=None,
        end_at_utc=None,
        initial_equity=10_000.0,
        costs={"commission_bps": 0.0, "slippage_bps": 0.0},
        seed_run_id_prefix="usage",
    )

    summary = pd.read_csv(result.summary_csv_path)
    assert len(summary) == 1
    row = summary.iloc[0].to_dict()
    assert row["strategy_share_available"] in (True, "True")
    assert row["strategy_share_error"] in ("", None) or str(row["strategy_share_error"]) == "nan"
    counts = json.loads(row["strategy_counts_json"])
    assert isinstance(counts, dict)
    assert counts

    decision_path = tmp_path / "usage_AAA_1m" / "decision_records.jsonl"
    decision_lines = [
        line for line in decision_path.read_text(encoding="utf-8").splitlines() if line
    ]
    assert sum(counts.values()) == len(decision_lines)

    primary = row["primary_strategy"]
    assert primary in counts
    expected_share = counts[primary] / float(len(decision_lines))
    assert float(row["primary_strategy_share"]) == pytest.approx(expected_share, rel=1e-12)


def test_strategy_share_missing_records(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _stub_run_backtest(
        df: pd.DataFrame,
        initial_equity: float,
        *,
        run_id: str,
        out_dir: Path,
        **_kwargs: object,
    ) -> BacktestResult:
        run_dir = Path(out_dir) / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        metrics_path = run_dir / "metrics.json"
        manifest_path = run_dir / "run_manifest.json"
        decision_records_path = run_dir / "decision_records.jsonl"
        trades_path = run_dir / "trades.parquet"

        metrics_path.write_text(
            json.dumps(
                {
                    "total_return": 0.01 if "BBB" in run_id else 0.02,
                    "max_drawdown": 0.2 if "BBB" in run_id else 0.1,
                    "num_trades": 1,
                    "total_costs": 0.0,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        manifest_path.write_text(
            json.dumps(
                {
                    "git_sha": None,
                    "pnl_method": "mark_to_market",
                    "end_of_run_position_handling": "close_on_end",
                    "strategy_switch_policy": "no_forced_flat_on_switch",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        trades_path.write_bytes(b"PAR1")

        if "AAA" not in run_id:
            decision_records_path.write_text(
                json.dumps(
                    {"selection": {"strategy_id": "S1"}}, sort_keys=True, separators=(",", ":")
                )
                + "\n",
                encoding="utf-8",
            )
        return BacktestResult(
            trades=pd.DataFrame(),
            metrics={},
            trades_path=trades_path,
            metrics_path=metrics_path,
            decision_records_path=decision_records_path,
            manifest_path=manifest_path,
        )

    monkeypatch.setattr("backtest.batch.run_backtest", _stub_run_backtest)

    df = _make_ohlcv(last_open=99.0)
    result = run_batch_backtests(
        {"AAA": df, "BBB": df},
        out_dir=tmp_path,
        timeframe="1m",
        start_at_utc=None,
        end_at_utc=None,
        initial_equity=10_000.0,
        costs={"commission_bps": 0.0, "slippage_bps": 0.0},
        seed_run_id_prefix="missing_records",
    )
    summary = pd.read_csv(result.summary_csv_path)
    assert set(summary["status"]) == {"OK"}
    row_aaa = summary.loc[summary["symbol"] == "AAA"].iloc[0].to_dict()
    assert row_aaa["strategy_share_available"] in (False, "False")
    assert row_aaa["strategy_counts_json"] == "{}"
    assert row_aaa["primary_strategy"] == "" or pd.isna(row_aaa["primary_strategy"])
    assert float(row_aaa["primary_strategy_share"]) == pytest.approx(0.0, rel=1e-12)
    assert isinstance(row_aaa["strategy_share_error"], str) and row_aaa["strategy_share_error"]

    row_bbb = summary.loc[summary["symbol"] == "BBB"].iloc[0].to_dict()
    assert row_bbb["strategy_share_available"] in (True, "True")
    assert json.loads(row_bbb["strategy_counts_json"]) == {"S1": 1}


def test_non_monotonic_timestamps_sets_repaired_flag(tmp_path: Path) -> None:
    df = _make_ohlcv(last_open=99.0)
    order = [0, 2, 1] + list(range(3, len(df)))
    df = df.iloc[order]
    assert not df.index.is_monotonic_increasing

    result = run_batch_backtests(
        {"AAA": df},
        out_dir=tmp_path,
        timeframe="1m",
        start_at_utc=None,
        end_at_utc=None,
        initial_equity=10_000.0,
        costs={"commission_bps": 0.0, "slippage_bps": 0.0},
        seed_run_id_prefix="repair",
    )

    summary = pd.read_csv(result.summary_csv_path)
    assert len(summary) == 1
    row = summary.iloc[0].to_dict()
    assert row["status"] == "OK"
    assert row["timestamp_repaired"] in (True, "True")
    assert row["timestamp_repaired_reason"] == "non_monotonic_sorted"

    summary_json = json.loads(result.summary_json_path.read_text(encoding="utf-8"))
    assert summary_json["counts"]["repaired_count"] == 1


def test_param_grid_runs_cartesian_product(tmp_path: Path) -> None:
    df = _make_ohlcv(last_open=99.0)
    result = run_batch_backtests(
        {"AAA": df},
        out_dir=tmp_path,
        timeframe="1m",
        start_at_utc=None,
        end_at_utc=None,
        initial_equity=10_000.0,
        costs={"commission_bps": 0.0, "slippage_bps": 0.0},
        seed_run_id_prefix="grid",
        param_grid={"commission_bps": [0.0, 10.0]},
    )

    run_dirs = sorted(
        p.name for p in tmp_path.iterdir() if p.is_dir() and p.name.startswith("grid_AAA_1m_")
    )
    assert len(run_dirs) == 2

    summary = pd.read_csv(result.summary_csv_path)
    assert len(summary) == 2
    assert summary["config_id"].nunique() == 2

    configs = [json.loads(value) for value in summary["config_json"].tolist()]
    commissions = sorted(float(cfg["params"]["commission_bps"]) for cfg in configs)
    assert commissions == [0.0, 10.0]

    summary_json = json.loads(result.summary_json_path.read_text(encoding="utf-8"))
    assert "AAA" in summary_json["best_worst_by_dataset"]
    dataset = summary_json["best_worst_by_dataset"]["AAA"]
    assert "by_total_return" in dataset
    assert "by_max_drawdown" in dataset
    assert (
        dataset["by_total_return"]["best"]["config_id"]
        != dataset["by_total_return"]["worst"]["config_id"]
    )


def test_run_id_collision_fails_soft(tmp_path: Path) -> None:
    df = _make_ohlcv(last_open=99.0)
    (tmp_path / "collision_AAA_1m").mkdir(parents=True, exist_ok=False)
    result = run_batch_backtests(
        {"AAA": df, "BBB": df},
        out_dir=tmp_path,
        timeframe="1m",
        start_at_utc=None,
        end_at_utc=None,
        initial_equity=10_000.0,
        costs={"commission_bps": 0.0, "slippage_bps": 0.0},
        seed_run_id_prefix="collision",
    )
    summary = pd.read_csv(result.summary_csv_path)
    row_aaa = summary.loc[summary["symbol"] == "AAA"].iloc[0].to_dict()
    assert row_aaa["status"] == "FAILED"
    assert row_aaa["error"] == "run_id_collision"
    row_bbb = summary.loc[summary["symbol"] == "BBB"].iloc[0].to_dict()
    assert row_bbb["status"] == "OK"


def test_drawdown_best_worst_ordering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _stub_run_backtest(
        df: pd.DataFrame,
        initial_equity: float,
        *,
        run_id: str,
        out_dir: Path,
        commission_bps: float = 0.0,
        **_kwargs: object,
    ) -> BacktestResult:
        run_dir = Path(out_dir) / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        metrics_path = run_dir / "metrics.json"
        manifest_path = run_dir / "run_manifest.json"
        decision_records_path = run_dir / "decision_records.jsonl"
        trades_path = run_dir / "trades.parquet"

        max_drawdown = 0.05 if commission_bps == 0.0 else 0.25
        metrics_path.write_text(
            json.dumps(
                {
                    "total_return": 0.02 if commission_bps == 0.0 else 0.01,
                    "max_drawdown": max_drawdown,
                    "num_trades": 1,
                    "total_costs": 0.0,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        manifest_path.write_text(
            json.dumps(
                {
                    "git_sha": None,
                    "pnl_method": "mark_to_market",
                    "end_of_run_position_handling": "close_on_end",
                    "strategy_switch_policy": "no_forced_flat_on_switch",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        decision_records_path.write_text(
            json.dumps({"selection": {"strategy_id": "S1"}}, sort_keys=True, separators=(",", ":"))
            + "\n",
            encoding="utf-8",
        )
        trades_path.write_bytes(b"PAR1")
        return BacktestResult(
            trades=pd.DataFrame(),
            metrics={},
            trades_path=trades_path,
            metrics_path=metrics_path,
            decision_records_path=decision_records_path,
            manifest_path=manifest_path,
        )

    monkeypatch.setattr("backtest.batch.run_backtest", _stub_run_backtest)
    df = _make_ohlcv(last_open=99.0)
    result = run_batch_backtests(
        {"AAA": df},
        out_dir=tmp_path,
        timeframe="1m",
        start_at_utc=None,
        end_at_utc=None,
        initial_equity=10_000.0,
        costs={"commission_bps": 0.0, "slippage_bps": 0.0},
        seed_run_id_prefix="dd",
        param_grid={"commission_bps": [0.0, 10.0]},
    )
    summary_json = json.loads(result.summary_json_path.read_text(encoding="utf-8"))
    dataset = summary_json["best_worst_by_dataset"]["AAA"]["by_max_drawdown"]
    assert dataset["ordering"] == "smaller_is_better"
    assert dataset["best"]["max_drawdown"] < dataset["worst"]["max_drawdown"]


def test_holdout_split_creates_paired_runs(tmp_path: Path) -> None:
    df = _make_ohlcv(last_open=99.0)
    result = run_batch_backtests(
        {"AAA": df},
        out_dir=tmp_path,
        timeframe="1m",
        start_at_utc=None,
        end_at_utc=None,
        initial_equity=10_000.0,
        costs={"commission_bps": 0.0, "slippage_bps": 0.0},
        seed_run_id_prefix="holdout",
        split={
            "type": "holdout",
            "train_frac": 0.7,
            "min_train_bars": 50,
            "min_test_bars": 20,
        },
    )

    assert (tmp_path / "holdout_AAA_1m__seg-TRAIN").exists()
    assert (tmp_path / "holdout_AAA_1m__seg-TEST").exists()

    summary = pd.read_csv(result.summary_csv_path)
    assert len(summary) == 2
    assert set(summary["segment"]) == {"TRAIN", "TEST"}
    assert set(summary["split_type"]) == {"holdout"}
    assert summary["pair_id"].nunique() == 1
    assert summary["window_index"].isna().all()

    summary_json = json.loads(result.summary_json_path.read_text(encoding="utf-8"))
    assert summary_json["schema_version"] == "batch_summary_v2"


def test_insufficient_bars_for_split_fails_soft(tmp_path: Path) -> None:
    too_short = _make_ohlcv_n(periods=40, last_open=99.0)
    ok = _make_ohlcv(last_open=99.0)
    result = run_batch_backtests(
        {"SHORT": too_short, "OK": ok},
        out_dir=tmp_path,
        timeframe="1m",
        start_at_utc=None,
        end_at_utc=None,
        initial_equity=10_000.0,
        costs={"commission_bps": 0.0, "slippage_bps": 0.0},
        seed_run_id_prefix="small",
        split={
            "type": "holdout",
            "train_frac": 0.7,
            "min_train_bars": 50,
            "min_test_bars": 20,
        },
    )

    summary = pd.read_csv(result.summary_csv_path)
    row_short = summary.loc[summary["symbol"] == "SHORT"].iloc[0].to_dict()
    assert row_short["status"] == "FAILED"
    assert row_short["error"] == "insufficient_bars_for_split"

    assert (tmp_path / "small_OK_1m__seg-TRAIN").exists()
    assert (tmp_path / "small_OK_1m__seg-TEST").exists()


def test_walk_forward_creates_multiple_windows(tmp_path: Path) -> None:
    df = _make_ohlcv_n(periods=100, last_open=99.0)
    result = run_batch_backtests(
        {"AAA": df},
        out_dir=tmp_path,
        timeframe="1m",
        start_at_utc=None,
        end_at_utc=None,
        initial_equity=10_000.0,
        costs={"commission_bps": 0.0, "slippage_bps": 0.0},
        seed_run_id_prefix="wf",
        split={
            "type": "walk_forward",
            "train_bars": 40,
            "test_bars": 20,
            "step_bars": 20,
        },
    )

    summary = pd.read_csv(result.summary_csv_path)
    assert len(summary) == 6
    assert set(summary["split_type"]) == {"walk_forward"}
    assert set(summary["segment"]) == {"TRAIN", "TEST"}
    assert sorted(summary["window_index"].dropna().unique().tolist()) == [0, 1, 2]
    assert summary.groupby("window_index").size().to_dict() == {0.0: 2, 1.0: 2, 2.0: 2}

    assert (tmp_path / "wf_AAA_1m__wf-0__seg-TRAIN").exists()
    assert (tmp_path / "wf_AAA_1m__wf-1__seg-TEST").exists()


def test_overfit_deltas_present(tmp_path: Path) -> None:
    df = _make_ohlcv(last_open=99.0)
    result = run_batch_backtests(
        {"AAA": df},
        out_dir=tmp_path,
        timeframe="1m",
        start_at_utc=None,
        end_at_utc=None,
        initial_equity=10_000.0,
        costs={"commission_bps": 0.0, "slippage_bps": 0.0},
        seed_run_id_prefix="delta",
        split={
            "type": "holdout",
            "train_frac": 0.7,
            "min_train_bars": 50,
            "min_test_bars": 20,
        },
    )

    summary_json = json.loads(result.summary_json_path.read_text(encoding="utf-8"))
    pairs = summary_json["overfit_pairs"]
    assert pairs
    assert all("delta_total_return" in item for item in pairs)
    assert all(isinstance(item["delta_total_return"], float) for item in pairs)


def test_pair_id_changes_with_any_component() -> None:
    base = _pair_id("AAA", "1m", "abc12345", None)
    assert base != _pair_id("BBB", "1m", "abc12345", None)
    assert base != _pair_id("AAA", "5m", "abc12345", None)
    assert base != _pair_id("AAA", "1m", "def67890", None)
    assert base != _pair_id("AAA", "1m", "abc12345", 0)
    assert _pair_id("AAA", "1m", "abc12345", 0) != _pair_id("AAA", "1m", "abc12345", 1)


def test_walk_forward_segments_do_not_overlap(tmp_path: Path) -> None:
    df = _make_ohlcv_n(periods=100, last_open=99.0)
    result = run_batch_backtests(
        {"AAA": df},
        out_dir=tmp_path,
        timeframe="1m",
        start_at_utc=None,
        end_at_utc=None,
        initial_equity=10_000.0,
        costs={"commission_bps": 0.0, "slippage_bps": 0.0},
        seed_run_id_prefix="wfo",
        split={
            "type": "walk_forward",
            "train_bars": 40,
            "test_bars": 20,
            "step_bars": 20,
        },
    )
    summary = pd.read_csv(result.summary_csv_path)
    for window_index in sorted(summary["window_index"].dropna().unique().tolist()):
        train_run_id = summary.loc[
            (summary["window_index"] == window_index) & (summary["segment"] == "TRAIN"),
            "run_id",
        ].iloc[0]
        test_run_id = summary.loc[
            (summary["window_index"] == window_index) & (summary["segment"] == "TEST"),
            "run_id",
        ].iloc[0]

        train_records = (
            (tmp_path / str(train_run_id) / "decision_records.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        test_records = (
            (tmp_path / str(test_run_id) / "decision_records.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        train_ts = [
            pd.to_datetime(json.loads(line)["ts_utc"], utc=True) for line in train_records if line
        ]
        test_ts = [
            pd.to_datetime(json.loads(line)["ts_utc"], utc=True) for line in test_records if line
        ]
        assert train_ts
        assert test_ts
        assert max(train_ts) < min(test_ts)


def test_rankings_exclude_failed_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _stub_run_backtest(
        df: pd.DataFrame,
        initial_equity: float,
        *,
        run_id: str,
        out_dir: Path,
        **_kwargs: object,
    ) -> BacktestResult:
        if "AAA" in run_id and "__seg-TEST" in run_id:
            raise ValueError("boom")

        run_dir = Path(out_dir) / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        metrics_path = run_dir / "metrics.json"
        manifest_path = run_dir / "run_manifest.json"
        decision_records_path = run_dir / "decision_records.jsonl"
        trades_path = run_dir / "trades.parquet"

        symbol = "AAA" if "AAA" in run_id else "BBB"
        segment = "TEST" if "__seg-TEST" in run_id else "TRAIN"
        metrics_path.write_text(
            json.dumps(
                {
                    "total_return": 0.10 if symbol == "BBB" and segment == "TEST" else 0.05,
                    "max_drawdown": 0.30 if symbol == "BBB" and segment == "TEST" else 0.10,
                    "num_trades": 1,
                    "total_costs": 0.0,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        manifest_path.write_text(
            json.dumps(
                {
                    "git_sha": None,
                    "pnl_method": "mark_to_market",
                    "end_of_run_position_handling": "close_on_end",
                    "strategy_switch_policy": "no_forced_flat_on_switch",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        decision_records_path.write_text(
            json.dumps({"selection": {"strategy_id": "S1"}, "ts_utc": "2026-02-01T00:00:00Z"})
            + "\n",
            encoding="utf-8",
        )
        trades_path.write_bytes(b"PAR1")
        return BacktestResult(
            trades=pd.DataFrame(),
            metrics={},
            trades_path=trades_path,
            metrics_path=metrics_path,
            decision_records_path=decision_records_path,
            manifest_path=manifest_path,
        )

    monkeypatch.setattr("backtest.batch.run_backtest", _stub_run_backtest)
    df = _make_ohlcv(last_open=99.0)
    result = run_batch_backtests(
        {"AAA": df, "BBB": df},
        out_dir=tmp_path,
        timeframe="1m",
        start_at_utc=None,
        end_at_utc=None,
        initial_equity=10_000.0,
        costs={"commission_bps": 0.0, "slippage_bps": 0.0},
        seed_run_id_prefix="rank",
        split={
            "type": "holdout",
            "train_frac": 0.7,
            "min_train_bars": 50,
            "min_test_bars": 20,
        },
    )
    summary_json = json.loads(result.summary_json_path.read_text(encoding="utf-8"))
    assert all("AAA" not in item["symbol"] for item in summary_json["top_by_test_return"])
    assert all("AAA" not in item["symbol"] for item in summary_json["worst_by_test_drawdown"])


def test_drawdown_ranking_picks_larger_as_worst(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _stub_run_backtest(
        df: pd.DataFrame,
        initial_equity: float,
        *,
        run_id: str,
        out_dir: Path,
        **_kwargs: object,
    ) -> BacktestResult:
        run_dir = Path(out_dir) / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        metrics_path = run_dir / "metrics.json"
        manifest_path = run_dir / "run_manifest.json"
        decision_records_path = run_dir / "decision_records.jsonl"
        trades_path = run_dir / "trades.parquet"

        symbol = "AAA" if "AAA" in run_id else "BBB"
        segment = "TEST" if "__seg-TEST" in run_id else "TRAIN"
        dd = (
            0.05
            if symbol == "AAA" and segment == "TEST"
            else 0.25
            if symbol == "BBB" and segment == "TEST"
            else 0.01
        )
        metrics_path.write_text(
            json.dumps(
                {"total_return": 0.01, "max_drawdown": dd, "num_trades": 1, "total_costs": 0.0},
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        manifest_path.write_text(
            json.dumps(
                {
                    "git_sha": None,
                    "pnl_method": "mark_to_market",
                    "end_of_run_position_handling": "close_on_end",
                    "strategy_switch_policy": "no_forced_flat_on_switch",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        decision_records_path.write_text(
            json.dumps({"selection": {"strategy_id": "S1"}, "ts_utc": "2026-02-01T00:00:00Z"})
            + "\n",
            encoding="utf-8",
        )
        trades_path.write_bytes(b"PAR1")
        return BacktestResult(
            trades=pd.DataFrame(),
            metrics={},
            trades_path=trades_path,
            metrics_path=metrics_path,
            decision_records_path=decision_records_path,
            manifest_path=manifest_path,
        )

    monkeypatch.setattr("backtest.batch.run_backtest", _stub_run_backtest)
    df = _make_ohlcv(last_open=99.0)
    result = run_batch_backtests(
        {"AAA": df, "BBB": df},
        out_dir=tmp_path,
        timeframe="1m",
        start_at_utc=None,
        end_at_utc=None,
        initial_equity=10_000.0,
        costs={"commission_bps": 0.0, "slippage_bps": 0.0},
        seed_run_id_prefix="ddrank",
        split={
            "type": "holdout",
            "train_frac": 0.7,
            "min_train_bars": 50,
            "min_test_bars": 20,
        },
    )
    summary_json = json.loads(result.summary_json_path.read_text(encoding="utf-8"))
    worst = summary_json["worst_by_test_drawdown"][0]
    assert worst["symbol"] == "BBB"

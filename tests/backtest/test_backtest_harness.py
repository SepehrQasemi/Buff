from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtest.harness import run_backtest
from buff.features.indicators import atr_wilder
from selector.types import SelectionResult
from strategies.runners import mean_revert_v1
from strategy_registry.decision import (
    DECISION_SCHEMA_VERSION,
    Decision,
    DecisionAction,
    DecisionProvenance,
    DecisionRisk,
)


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


def test_backtest_golden(tmp_path: Path) -> None:
    df = _make_ohlcv()
    result = run_backtest(df, 10_000.0, run_id="bt", out_dir=tmp_path)

    trades = result.trades
    assert len(trades) == 2
    assert trades.iloc[0]["side"] == "BUY"
    assert trades.iloc[1]["side"] == "SELL"

    entry_price = trades.iloc[0]["price"]
    assert entry_price == pytest.approx(99.0, rel=1e-9)

    close = pd.Series(df["close"].to_numpy())
    high = pd.Series(df["high"].to_numpy())
    low = pd.Series(df["low"].to_numpy())
    atr = atr_wilder(high, low, close, period=14).iloc[-2]
    atr_eff = max(float(atr), mean_revert_v1.ATR_EPS)
    stop_distance = mean_revert_v1.ATR_STOP_MULT * atr_eff
    risk_entry_price = float(close.iloc[-2])
    expected_qty = (mean_revert_v1.DEFAULT_EQUITY * mean_revert_v1.RISK_PCT) / stop_distance
    expected_qty = min(
        expected_qty,
        mean_revert_v1.MAX_NOTIONAL / risk_entry_price,
        mean_revert_v1.MAX_POSITION_SIZE,
    )
    expected_stop = risk_entry_price - stop_distance
    expected_pnl = (expected_stop - entry_price) * expected_qty

    assert trades.iloc[0]["qty"] == pytest.approx(expected_qty, rel=1e-9)
    assert trades.iloc[1]["price"] == pytest.approx(expected_stop, rel=1e-9)
    assert trades.iloc[1]["pnl"] == pytest.approx(expected_pnl, rel=1e-6)
    assert trades.iloc[1]["equity_after"] == pytest.approx(10_000.0 + expected_pnl, rel=1e-6)

    metrics = result.metrics
    assert metrics["num_trades"] == 1
    expected_return = expected_pnl / 10_000.0
    assert metrics["total_return"] == pytest.approx(expected_return, rel=1e-6)
    assert metrics["max_drawdown"] == pytest.approx(-expected_return, rel=1e-6)
    assert metrics["win_rate"] == pytest.approx(0.0, rel=1e-9)
    assert metrics["avg_loss"] == pytest.approx(expected_pnl, rel=1e-6)

    assert result.trades_path.exists()
    assert result.metrics_path.exists()
    assert result.decision_records_path.exists()
    assert result.manifest_path.exists()

    metrics_payload = json.loads(result.metrics_path.read_text(encoding="utf-8"))
    assert metrics_payload["pnl_method"] == "mark_to_market"
    assert metrics_payload["end_of_run_position_handling"] == "close_on_end"
    assert metrics_payload["strategy_switch_policy"] == "no_forced_flat_on_switch"
    assert metrics_payload["total_costs"] == pytest.approx(0.0, rel=1e-12)
    assert metrics_payload["costs_breakdown"] == {"commission": 0.0, "slippage": 0.0}

    manifest_payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest_payload["pnl_method"] == "mark_to_market"
    assert manifest_payload["end_of_run_position_handling"] == "close_on_end"
    assert manifest_payload["strategy_switch_policy"] == "no_forced_flat_on_switch"

    records = result.decision_records_path.read_text(encoding="utf-8").strip().splitlines()
    assert records
    payload = json.loads(records[-1])
    selection = payload["selection"]
    assert selection.get("strategy_id")
    assert selection.get("provenance")


def test_backtest_uses_next_open(tmp_path: Path) -> None:
    df = _make_ohlcv()
    df.iloc[-1, df.columns.get_loc("open")] = 101.0
    result = run_backtest(df, 10_000.0, run_id="bt_next_open", out_dir=tmp_path)
    trades = result.trades
    assert trades.iloc[0]["price"] == pytest.approx(101.0, rel=1e-9)


def test_stop_tp_tie_break(tmp_path: Path) -> None:
    df = _make_ohlcv()
    df.iloc[-1, df.columns.get_loc("open")] = 99.0
    df.iloc[-1, df.columns.get_loc("high")] = 110.0
    df.iloc[-1, df.columns.get_loc("low")] = 90.0
    result = run_backtest(df, 10_000.0, run_id="bt_tie", out_dir=tmp_path)
    trades = result.trades
    assert len(trades) == 2
    assert trades.iloc[1]["side"] == "SELL"
    assert trades.iloc[1]["price"] < trades.iloc[0]["price"]


def test_decision_records_are_per_run(tmp_path: Path) -> None:
    df = _make_ohlcv()
    res_a = run_backtest(df, 10_000.0, run_id="run_a", out_dir=tmp_path)
    res_b = run_backtest(df, 10_000.0, run_id="run_b", out_dir=tmp_path)
    assert res_a.decision_records_path != res_b.decision_records_path
    assert res_a.decision_records_path.exists()
    assert res_b.decision_records_path.exists()
    content_a = res_a.decision_records_path.read_text(encoding="utf-8")
    content_b = res_b.decision_records_path.read_text(encoding="utf-8")
    assert content_a
    assert content_b


def test_as_of_utc_no_leak(tmp_path: Path) -> None:
    df = _make_ohlcv()
    cutoff = df.index[-2]
    res_full = run_backtest(
        df,
        10_000.0,
        run_id="full",
        out_dir=tmp_path,
        end_at_utc=cutoff.isoformat().replace("+00:00", "Z"),
    )
    df_trunc = df.loc[:cutoff]
    res_trunc = run_backtest(df_trunc, 10_000.0, run_id="trunc", out_dir=tmp_path)

    rec_full = res_full.decision_records_path.read_text(encoding="utf-8").strip().splitlines()
    rec_trunc = res_trunc.decision_records_path.read_text(encoding="utf-8").strip().splitlines()
    assert rec_full
    assert rec_trunc
    target = df_trunc.index[-2].isoformat().replace("+00:00", "Z")

    def _find_selection(lines: list[str], as_of: str) -> dict:
        for line in lines:
            selection = json.loads(line)["selection"]
            if selection.get("as_of_utc") == as_of:
                return selection
        raise AssertionError("as_of_not_found")

    payload_full = _find_selection(rec_full, target)
    payload_trunc = _find_selection(rec_trunc, target)
    assert payload_full["decision_action"] == payload_trunc["decision_action"]


def test_costs_reduce_pnl(tmp_path: Path) -> None:
    df = _make_ohlcv()
    no_costs = run_backtest(df, 10_000.0, run_id="no_costs", out_dir=tmp_path)
    with_costs = run_backtest(
        df,
        10_000.0,
        run_id="with_costs",
        out_dir=tmp_path,
        commission_bps=10.0,
        slippage_bps=5.0,
    )

    assert with_costs.trades.iloc[-1]["equity_after"] < no_costs.trades.iloc[-1]["equity_after"]
    assert with_costs.metrics["total_return"] < no_costs.metrics["total_return"]

    metrics_payload = json.loads(with_costs.metrics_path.read_text(encoding="utf-8"))
    assert metrics_payload["total_costs"] > 0.0
    breakdown = metrics_payload["costs_breakdown"]
    assert breakdown["commission"] > 0.0
    assert breakdown["slippage"] > 0.0


def test_close_on_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    idx = pd.date_range("2026-02-01", periods=3, freq="min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0],
            "high": [101.0, 101.0, 101.0],
            "low": [99.0, 99.0, 99.0],
            "close": [100.0, 100.0, 100.0],
            "volume": [1000.0, 1000.0, 1000.0],
        },
        index=idx,
    )
    df.index.name = "timestamp"

    monkeypatch.setattr(
        "backtest.harness.select_strategy",
        lambda *_args, **_kwargs: SelectionResult(
            strategy_id="DUMMY",
            reason="test",
            rule_id="test",
            inputs={},
        ),
    )
    monkeypatch.setattr("backtest.harness._resolve_strategy_id", lambda _name: "DUMMY@1")

    class _DummySpec:
        version = 1

    class _DummyStrategy:
        spec = _DummySpec()

    monkeypatch.setattr("backtest.harness.get_strategy", lambda _id: _DummyStrategy())

    call_count = {"n": 0}

    def _stub_run_strategy(_strategy, _features_df, metadata, as_of_utc: str) -> Decision:
        action = DecisionAction.ENTER_LONG if call_count["n"] == 0 else DecisionAction.HOLD
        call_count["n"] += 1
        return Decision(
            schema_version=DECISION_SCHEMA_VERSION,
            as_of_utc=as_of_utc,
            instrument=str(metadata["instrument"]),
            action=action,
            rationale=["test"],
            risk=DecisionRisk(
                max_position_size=1.0,
                stop_loss=1.0,
                take_profit=1_000_000.0,
            ),
            provenance=DecisionProvenance(
                feature_bundle_fingerprint=str(metadata["bundle_fingerprint"]),
                strategy_id="DUMMY@1",
                strategy_params_hash="0" * 64,
            ),
            confidence=0.5,
        )

    monkeypatch.setattr("backtest.harness.run_strategy", _stub_run_strategy)

    result = run_backtest(df, 10_000.0, run_id="close_on_end", out_dir=tmp_path)
    assert len(result.trades) == 2
    assert result.trades.iloc[0]["side"] == "BUY"
    assert result.trades.iloc[-1]["side"] == "SELL"
    assert result.trades.iloc[-1]["reason"] == "close_on_end"
    assert result.trades.iloc[-1]["price"] == pytest.approx(100.0, rel=1e-12)

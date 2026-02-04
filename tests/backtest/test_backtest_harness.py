from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtest.harness import run_backtest
from buff.features.indicators import atr_wilder
from strategies.runners import mean_revert_v1


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

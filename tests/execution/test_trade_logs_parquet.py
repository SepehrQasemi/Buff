from __future__ import annotations

from pathlib import Path

import pandas as pd

from control_plane.state import ControlState, SystemState
from execution.engine import execute_paper_run
from execution.trade_log import TRADE_SCHEMA, write_trades_parquet


def test_trade_log_schema_and_ordering(tmp_path: Path) -> None:
    path = tmp_path / "trades.parquet"
    trades = [
        {
            "run_id": "run-1",
            "ts_utc": "2026-02-01T00:00:01Z",
            "order_id": "b",
            "symbol": "ETHUSDT",
            "side": "buy",
            "qty": 2.0,
            "status": "filled",
            "reason": "",
            "execution_status": "EXECUTED",
        },
        {
            "run_id": "run-1",
            "ts_utc": "2026-02-01T00:00:00Z",
            "order_id": "a",
            "symbol": "BTCUSDT",
            "side": "sell",
            "qty": 1.0,
            "status": "filled",
            "reason": "",
            "execution_status": "EXECUTED",
        },
    ]
    write_trades_parquet(path, trades)
    df = pd.read_parquet(path, engine="pyarrow")
    assert list(df.columns) == list(TRADE_SCHEMA.names)
    assert df["order_id"].tolist() == ["a", "b"]


def test_execute_paper_run_writes_empty_trades(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _ = execute_paper_run(
        input_data={"run_id": "run1", "timeframe": "1m"},
        features={},
        risk_decision={"risk_state": "GREEN"},
        selected_strategy={"name": "demo", "version": "1.0.0"},
        control_state=ControlState(state=SystemState.DISARMED),
    )
    trades_path = Path("workspaces/run1/trades.parquet")
    assert trades_path.exists()
    df = pd.read_parquet(trades_path, engine="pyarrow")
    assert df.empty
    assert list(df.columns) == list(TRADE_SCHEMA.names)

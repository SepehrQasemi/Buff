from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from control_plane.control import kill_switch
from control_plane.state import ControlState, SystemState
from decision_records.schema import validate_decision_record
from execution.engine import execute_paper_run
from execution.trade_log import TRADE_SCHEMA


def test_kill_switch_blocks_and_records(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    state = kill_switch(ControlState(state=SystemState.ARMED), "kill_switch")
    out = execute_paper_run(
        input_data={"run_id": "run1", "timeframe": "1m"},
        features={},
        risk_decision={"risk_state": "GREEN"},
        selected_strategy={"name": "demo", "version": "1.0.0"},
        control_state=state,
    )
    assert out["status"] == "blocked"
    record = json.loads(Path("workspaces/run1/decision_records.jsonl").read_text())
    validate_decision_record(record)
    assert record["execution_status"] == "BLOCKED"
    assert record["reason"] == "kill_switch"
    trades_path = Path("workspaces/run1/trades.parquet")
    assert trades_path.exists()
    df = pd.read_parquet(trades_path, engine="pyarrow")
    assert df.empty
    assert list(df.columns) == list(TRADE_SCHEMA.names)

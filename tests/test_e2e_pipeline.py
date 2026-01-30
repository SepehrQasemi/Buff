from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from control_plane.control import arm
from control_plane.state import ControlConfig, Environment, SystemState
from decision_records.schema import validate_decision_record
from execution.engine import execute_paper_run


def test_e2e_pipeline_writes_valid_record(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _ = pd.DataFrame(
        {
            "ts": pd.date_range("2023-01-01", periods=3, freq="1min", tz="UTC"),
            "open": [1.0, 1.0, 1.0],
            "high": [1.0, 1.0, 1.0],
            "low": [1.0, 1.0, 1.0],
            "close": [1.0, 1.0, 1.0],
            "volume": [1.0, 1.0, 1.0],
        }
    )

    control_state = arm(
        ControlConfig(environment=Environment.PAPER, required_approvals={"ok"}),
        approvals=["ok"],
    )
    assert control_state.state == SystemState.ARMED

    out = execute_paper_run(
        input_data={
            "run_id": "e2e",
            "timeframe": "1m",
            "market_state": {"trend_state": "UP"},
        },
        features={"close": [1.0, 1.0, 1.0]},
        risk_decision={"risk_state": "GREEN"},
        selected_strategy={"name": "dummy", "version": "1.0.0"},
        control_state=control_state,
    )
    assert out["status"] == "ok"

    records_path = Path("workspaces") / "e2e" / "decision_records.jsonl"
    record = json.loads(records_path.read_text(encoding="utf-8").strip())
    validate_decision_record(record)

from __future__ import annotations

import json
from pathlib import Path

from control_plane.state import ControlState, SystemState
from decision_records.schema import validate_decision_record
from execution.engine import execute_paper_run


def test_disarmed_blocks_and_records(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    out = execute_paper_run(
        input_data={"run_id": "run1", "timeframe": "1m", "market_state": {}},
        features={},
        risk_decision={"risk_state": "GREEN"},
        selected_strategy={"name": "s1", "version": "1.0.0"},
        control_state=ControlState(state=SystemState.DISARMED),
    )
    assert out["status"] == "blocked"
    path = Path("workspaces") / "run1" / "decision_records.jsonl"
    record = json.loads(path.read_text(encoding="utf-8").strip())
    validate_decision_record(record)
    assert record["execution_status"] == "BLOCKED"
    assert record["reason"] == "control_not_armed"


def test_risk_red_blocks_and_records(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    out = execute_paper_run(
        input_data={"run_id": "run1", "timeframe": "1m", "market_state": {}},
        features={},
        risk_decision={"risk_state": "RED"},
        selected_strategy={"name": "s1", "version": "1.0.0"},
        control_state=ControlState(state=SystemState.ARMED),
    )
    assert out["status"] == "blocked"
    path = Path("workspaces") / "run1" / "decision_records.jsonl"
    record = json.loads(path.read_text(encoding="utf-8").strip())
    validate_decision_record(record)
    assert record["execution_status"] == "BLOCKED"
    assert record["reason"] == "risk_veto"


def test_armed_green_writes_record(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    out = execute_paper_run(
        input_data={"run_id": "run1", "timeframe": "1m", "market_state": {}},
        features={},
        risk_decision={"risk_state": "GREEN"},
        selected_strategy={"name": "s1", "version": "1.0.0"},
        control_state=ControlState(state=SystemState.ARMED),
    )
    assert out["status"] == "executed"
    path = Path("workspaces") / "run1" / "decision_records.jsonl"
    record = json.loads(path.read_text(encoding="utf-8").strip())
    validate_decision_record(record)
    assert record["execution_status"] == "EXECUTED"

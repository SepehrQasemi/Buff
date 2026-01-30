from __future__ import annotations

import json
from pathlib import Path

import pytest

from control_plane.state import ControlState, SystemState
from decision_records.schema import validate_decision_record
from execution.engine import execute_paper_run


def _base_inputs() -> dict:
    return {"run_id": "run1", "timeframe": "1m"}


def _strategy() -> dict:
    return {"name": "demo", "version": "1.0.0"}


def test_disarmed_blocks_and_records(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    out = execute_paper_run(
        input_data=_base_inputs(),
        features={},
        risk_decision={"risk_state": "GREEN"},
        selected_strategy=_strategy(),
        control_state=ControlState(state=SystemState.DISARMED),
    )
    assert out["status"] == "blocked"
    path = Path("workspaces/run1/decision_records.jsonl")
    record = json.loads(path.read_text(encoding="utf-8").strip())
    validate_decision_record(record)
    assert record["execution_status"] == "BLOCKED"
    assert record["reason"]


def test_risk_red_blocks(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    out = execute_paper_run(
        input_data=_base_inputs(),
        features={},
        risk_decision={"risk_state": "RED"},
        selected_strategy=_strategy(),
        control_state=ControlState(state=SystemState.ARMED),
    )
    assert out["status"] == "blocked"
    record = json.loads(Path("workspaces/run1/decision_records.jsonl").read_text(encoding="utf-8").strip())
    assert record["execution_status"] == "BLOCKED"
    assert record["reason"]


def test_green_armed_executes(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    out = execute_paper_run(
        input_data=_base_inputs(),
        features={},
        risk_decision={"risk_state": "GREEN"},
        selected_strategy=_strategy(),
        control_state=ControlState(state=SystemState.ARMED),
    )
    assert out["status"] == "ok"
    record = json.loads(Path("workspaces/run1/decision_records.jsonl").read_text(encoding="utf-8").strip())
    assert record["schema_version"] == "1.0"
    assert record["inputs_digest"]


def test_run_id_traversal_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        execute_paper_run(
            input_data={"run_id": "../bad", "timeframe": "1m"},
            features={},
            risk_decision={"risk_state": "GREEN"},
            selected_strategy=_strategy(),
            control_state=ControlState(state=SystemState.ARMED),
        )
    assert not Path("workspaces").exists()

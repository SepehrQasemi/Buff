from __future__ import annotations

import json
from pathlib import Path

import pytest

from control_plane.state import ControlState, SystemState
from execution.engine import execute_paper_run


def test_disarmed_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError):
        execute_paper_run(
            input_data={"run_id": "run1", "timeframe": "1m"},
            features={},
            risk_decision={"risk_state": "GREEN"},
            selected_strategy={"strategy_id": "s1"},
            control_state=ControlState(state=SystemState.DISARMED),
        )


def test_risk_red_blocks_and_records(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    out = execute_paper_run(
        input_data={"run_id": "run1", "timeframe": "1m", "market_state": {}},
        features={},
        risk_decision={"risk_state": "RED"},
        selected_strategy={"strategy_id": "s1"},
        control_state=ControlState(state=SystemState.ARMED),
    )
    assert out["status"] == "blocked"
    path = Path("workspaces") / "run1" / "decision_records.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["selection"]["status"] == "blocked"


def test_armed_green_writes_record(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    out = execute_paper_run(
        input_data={"run_id": "run1", "timeframe": "1m", "market_state": {}},
        features={},
        risk_decision={"risk_state": "GREEN"},
        selected_strategy={"strategy_id": "s1"},
        control_state=ControlState(state=SystemState.ARMED),
    )
    assert out["status"] == "ok"
    path = Path("workspaces") / "run1" / "decision_records.jsonl"
    assert path.exists()

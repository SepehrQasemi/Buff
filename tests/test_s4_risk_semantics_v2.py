from __future__ import annotations

import json
from pathlib import Path

import pytest

from control_plane.state import ControlState, SystemState
from execution.engine import execute_paper_run
from risk.contracts import RiskConfig, RiskInputs, RiskReason, risk_inputs_digest
from risk.state_machine import evaluate_risk
from risk.veto import risk_veto


pytestmark = pytest.mark.unit


def _config(*, config_version: str = "v2") -> RiskConfig:
    return RiskConfig(
        missing_red=0.2,
        atr_yellow=0.02,
        atr_red=0.05,
        rvol_yellow=0.02,
        rvol_red=0.05,
        config_version=config_version,
    )


def _inputs(**overrides: object) -> RiskInputs:
    payload = {
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "as_of": "2024-01-01T00:00:00+00:00",
        "atr_pct": 0.01,
        "realized_vol": 0.01,
        "missing_fraction": 0.0,
        "timestamps_valid": True,
        "latest_metrics_valid": True,
        "invalid_index": False,
        "invalid_close": False,
    }
    payload.update(overrides)
    return RiskInputs(**payload)


def test_risk_decision_has_reasons_on_deny() -> None:
    decision = evaluate_risk(_inputs(missing_fraction=0.9), _config())
    assert decision.state.value == "RED"
    assert decision.reasons
    first_reason = decision.reasons[0]
    assert isinstance(first_reason, RiskReason)
    assert first_reason.rule_id
    assert first_reason.message


def test_risk_inputs_digest_stable() -> None:
    decision_a = evaluate_risk(_inputs(atr_pct=0.03), _config())
    decision_b = evaluate_risk(_inputs(atr_pct=0.03), _config())
    assert decision_a.inputs_digest == decision_b.inputs_digest

    payload_a = {"a": 1, "b": {"x": 2, "y": [1, 2, 3]}}
    payload_b = {"b": {"y": [1, 2, 3], "x": 2}, "a": 1}
    assert risk_inputs_digest(payload_a) == risk_inputs_digest(payload_b)


def test_risk_config_version_stable() -> None:
    cfg = _config(config_version="risk-semantics-v2")
    decision = evaluate_risk(_inputs(), cfg)
    assert decision.config_version == "risk-semantics-v2"

    deny_decision, _audit = risk_veto({"symbol": "BTCUSDT"}, cfg)
    assert deny_decision.config_version == "risk-semantics-v2"
    assert deny_decision.state.value == "RED"


def test_risk_artifact_contains_risk_reasons(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = execute_paper_run(
        input_data={"run_id": "run-v2", "timeframe": "1m"},
        features={},
        risk_decision={
            "risk_state": "RED",
            "config_version": "risk-semantics-v2",
            "reasons": [
                {
                    "rule_id": "atr_pct_above_red",
                    "severity": "ERROR",
                    "message": "ATR percent exceeded RED threshold",
                    "details": {"atr_pct": 0.1, "threshold": 0.05},
                }
            ],
        },
        selected_strategy={"name": "demo", "version": "1.0.0"},
        control_state=ControlState(state=SystemState.ARMED),
    )
    assert result["status"] == "blocked"

    raw = (Path("workspaces") / "run-v2" / "decision_records.jsonl").read_text(encoding="utf-8")
    record = json.loads(raw.strip())
    assert "risk" in record
    risk_block = record["risk"]
    assert set(risk_block.keys()) == {
        "decision",
        "permission",
        "reasons",
        "config_version",
        "inputs_digest",
    }
    assert risk_block["decision"] == "RED"
    assert risk_block["config_version"] == "risk-semantics-v2"
    assert isinstance(risk_block["inputs_digest"], str) and risk_block["inputs_digest"]
    assert isinstance(risk_block["reasons"], list) and risk_block["reasons"]
    first_reason = risk_block["reasons"][0]
    assert set(first_reason.keys()) == {"rule_id", "severity", "message", "details"}
    assert first_reason["rule_id"] == "atr_pct_above_red"

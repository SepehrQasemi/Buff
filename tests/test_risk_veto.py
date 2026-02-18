"""Tests for risk veto integration."""

from __future__ import annotations

import pytest

from risk.contracts import RiskInputs
from risk.contracts import RiskConfig, RiskState
from risk.state_machine import evaluate_risk
from risk.veto import risk_veto


pytestmark = pytest.mark.unit


def _config() -> RiskConfig:
    return RiskConfig(
        missing_red=0.2,
        atr_yellow=0.02,
        atr_red=0.05,
        rvol_yellow=0.02,
        rvol_red=0.05,
    )


def _inputs() -> RiskInputs:
    return RiskInputs(
        symbol="BTCUSDT",
        timeframe="1h",
        as_of="2024-01-01T00:00:00+00:00",
        atr_pct=0.01,
        realized_vol=0.01,
        missing_fraction=0.0,
        timestamps_valid=True,
        latest_metrics_valid=True,
        invalid_index=False,
        invalid_close=False,
    )


def test_invalid_inputs_fail_closed() -> None:
    decision, audit_event = risk_veto({"symbol": "BTCUSDT"}, _config())
    assert decision.state is RiskState.RED
    assert decision.reasons == ["invalid_inputs"]
    assert audit_event.component == "risk_veto"
    assert audit_event.action == "evaluate"


def test_valid_inputs_match_evaluate_risk() -> None:
    inputs = _inputs()
    cfg = _config()
    expected = evaluate_risk(inputs, cfg)
    decision, _audit_event = risk_veto(inputs, cfg)
    assert decision.state is expected.state
    assert decision.reasons == expected.reasons


def test_inputs_hash_stable() -> None:
    inputs = _inputs()
    cfg = _config()
    decision_one, audit_one = risk_veto(inputs, cfg)
    decision_two, audit_two = risk_veto(inputs, cfg)
    assert decision_one.snapshot == decision_two.snapshot
    assert audit_one.inputs_hash == audit_two.inputs_hash


def test_fail_closed_on_audit_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr("risk.veto.make_audit_event", _boom)
    decision, audit_event = risk_veto(_inputs(), _config())
    assert decision.state is RiskState.RED
    assert decision.reasons in (["invalid_inputs"], ["audit_error"])
    assert audit_event.component == "risk_veto"

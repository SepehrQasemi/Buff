"""Tests for risk state machine transitions."""

from __future__ import annotations

import pytest

from risk.contracts import RiskInputs
from risk.contracts import RiskConfig, RiskDecision, RiskState
from risk.state_machine import evaluate_risk


pytestmark = pytest.mark.unit


def _base_inputs() -> RiskInputs:
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


def _config() -> RiskConfig:
    return RiskConfig(
        missing_red=0.2,
        atr_yellow=0.02,
        atr_red=0.05,
        rvol_yellow=0.02,
        rvol_red=0.05,
        no_metrics_state=RiskState.YELLOW,
    )


def _assert_snapshot(decision: RiskDecision) -> None:
    keys = {
        "missing_fraction",
        "atr_pct",
        "realized_vol",
        "timestamps_valid",
        "latest_metrics_valid",
        "invalid_index",
        "invalid_close",
    }
    assert set(decision.snapshot.keys()) == keys


@pytest.mark.parametrize(
    "field,reason",
    [
        ("timestamps_valid", "invalid_timestamps"),
        ("latest_metrics_valid", "missing_metrics"),
        ("invalid_index", "invalid_index"),
        ("invalid_close", "invalid_close"),
    ],
)
def test_health_flags_force_red(field: str, reason: str) -> None:
    inputs = _base_inputs()
    inputs = RiskInputs(**{**inputs.to_dict(), field: False})
    if field in {"invalid_index", "invalid_close"}:
        inputs = RiskInputs(**{**inputs.to_dict(), field: True})
    decision = evaluate_risk(inputs, _config())
    assert decision.state is RiskState.RED
    assert reason in decision.reasons
    _assert_snapshot(decision)


def test_missing_fraction_boundary() -> None:
    cfg = _config()
    inputs = _base_inputs()
    inputs = RiskInputs(**{**inputs.to_dict(), "missing_fraction": cfg.missing_red})
    decision = evaluate_risk(inputs, cfg)
    assert decision.state is RiskState.GREEN

    inputs = RiskInputs(**{**inputs.to_dict(), "missing_fraction": cfg.missing_red + 0.01})
    decision = evaluate_risk(inputs, cfg)
    assert decision.state is RiskState.RED
    assert "missing_fraction_exceeded" in decision.reasons


def test_atr_only_cases() -> None:
    cfg = _config()
    inputs = _base_inputs()
    inputs = RiskInputs(**{**inputs.to_dict(), "realized_vol": None})

    decision = evaluate_risk(RiskInputs(**{**inputs.to_dict(), "atr_pct": 0.01}), cfg)
    assert decision.state is RiskState.GREEN

    decision = evaluate_risk(RiskInputs(**{**inputs.to_dict(), "atr_pct": 0.03}), cfg)
    assert decision.state is RiskState.YELLOW
    assert "atr_pct_above_yellow" in decision.reasons

    decision = evaluate_risk(RiskInputs(**{**inputs.to_dict(), "atr_pct": 0.06}), cfg)
    assert decision.state is RiskState.RED
    assert "atr_pct_above_red" in decision.reasons


def test_rvol_only_cases() -> None:
    cfg = _config()
    inputs = _base_inputs()
    inputs = RiskInputs(**{**inputs.to_dict(), "atr_pct": None})

    decision = evaluate_risk(RiskInputs(**{**inputs.to_dict(), "realized_vol": 0.01}), cfg)
    assert decision.state is RiskState.GREEN

    decision = evaluate_risk(RiskInputs(**{**inputs.to_dict(), "realized_vol": 0.03}), cfg)
    assert decision.state is RiskState.YELLOW
    assert "realized_vol_above_yellow" in decision.reasons

    decision = evaluate_risk(RiskInputs(**{**inputs.to_dict(), "realized_vol": 0.06}), cfg)
    assert decision.state is RiskState.RED
    assert "realized_vol_above_red" in decision.reasons


def test_combined_metrics_red_dominates() -> None:
    cfg = _config()
    inputs = _base_inputs()
    inputs = RiskInputs(**{**inputs.to_dict(), "atr_pct": 0.06, "realized_vol": 0.03})
    decision = evaluate_risk(inputs, cfg)
    assert decision.state is RiskState.RED
    assert "atr_pct_above_red" in decision.reasons


def test_no_metrics_defaults_to_yellow() -> None:
    cfg = _config()
    inputs = _base_inputs()
    inputs = RiskInputs(**{**inputs.to_dict(), "atr_pct": None, "realized_vol": None})
    decision = evaluate_risk(inputs, cfg)
    assert decision.state is RiskState.YELLOW
    assert decision.reasons == ["no_metrics"]

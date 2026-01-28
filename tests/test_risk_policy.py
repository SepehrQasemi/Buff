"""Unit tests for risk policy decisions."""

from __future__ import annotations

from risk.policy import evaluate_policy
from risk.types import Permission, RiskConfig, RiskInputs, RiskState


def test_policy_green() -> None:
    config = RiskConfig()
    decision = evaluate_policy(
        RiskInputs(
            atr_pct=0.005,
            realized_vol=0.005,
            missing_fraction=0.0,
            timestamps_valid=True,
            latest_metrics_valid=True,
            invalid_index=False,
            invalid_close=False,
        ),
        config,
    )
    assert decision.state == RiskState.GREEN
    assert decision.permission == Permission.ALLOW
    assert decision.recommended_scale == 1.0
    assert decision.reasons == ()


def test_policy_yellow() -> None:
    config = RiskConfig()
    decision = evaluate_policy(
        RiskInputs(
            atr_pct=0.015,
            realized_vol=0.005,
            missing_fraction=0.0,
            timestamps_valid=True,
            latest_metrics_valid=True,
            invalid_index=False,
            invalid_close=False,
        ),
        config,
    )
    assert decision.state == RiskState.YELLOW
    assert decision.permission == Permission.RESTRICT
    assert "atr_pct_between_yellow_red" in decision.reasons


def test_policy_red_threshold() -> None:
    config = RiskConfig()
    decision = evaluate_policy(
        RiskInputs(
            atr_pct=0.03,
            realized_vol=0.005,
            missing_fraction=0.0,
            timestamps_valid=True,
            latest_metrics_valid=True,
            invalid_index=False,
            invalid_close=False,
        ),
        config,
    )
    assert decision.state == RiskState.RED
    assert decision.permission == Permission.BLOCK
    assert "atr_pct_above_red" in decision.reasons


def test_policy_red_missing_fraction() -> None:
    config = RiskConfig()
    decision = evaluate_policy(
        RiskInputs(
            atr_pct=0.005,
            realized_vol=0.005,
            missing_fraction=0.5,
            timestamps_valid=True,
            latest_metrics_valid=True,
            invalid_index=False,
            invalid_close=False,
        ),
        config,
    )
    assert decision.state == RiskState.RED
    assert "missing_fraction_exceeded" in decision.reasons


def test_policy_red_invalid_timestamps() -> None:
    config = RiskConfig()
    decision = evaluate_policy(
        RiskInputs(
            atr_pct=0.005,
            realized_vol=0.005,
            missing_fraction=0.0,
            timestamps_valid=False,
            latest_metrics_valid=True,
            invalid_index=False,
            invalid_close=False,
        ),
        config,
    )
    assert decision.state == RiskState.RED
    assert "invalid_timestamps" in decision.reasons


def test_policy_red_invalid_index() -> None:
    config = RiskConfig()
    decision = evaluate_policy(
        RiskInputs(
            atr_pct=0.005,
            realized_vol=0.005,
            missing_fraction=0.0,
            timestamps_valid=True,
            latest_metrics_valid=True,
            invalid_index=True,
            invalid_close=False,
        ),
        config,
    )
    assert decision.state == RiskState.RED
    assert "invalid_index" in decision.reasons


def test_policy_red_invalid_close() -> None:
    config = RiskConfig()
    decision = evaluate_policy(
        RiskInputs(
            atr_pct=0.005,
            realized_vol=0.005,
            missing_fraction=0.0,
            timestamps_valid=True,
            latest_metrics_valid=True,
            invalid_index=False,
            invalid_close=True,
        ),
        config,
    )
    assert decision.state == RiskState.RED
    assert "invalid_close" in decision.reasons

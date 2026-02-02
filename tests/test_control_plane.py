from __future__ import annotations

from pathlib import Path

import pytest

from control_plane.core import ControlPlane, ControlPlaneState
from execution.locks import RiskLocks
from execution.types import IntentSide, OrderIntent
from risk.contracts import RiskInputs
from risk.state_machine import RiskConfig as GateRiskConfig
from risk.types import Permission, RiskState
from strategies.registry import StrategyRegistry, StrategySpec
from ui.api import UIContext, arm_live, run_paper


def _intent() -> OrderIntent:
    return OrderIntent(
        event_id="evt-10",
        intent_id="intent-10",
        symbol="BTCUSDT",
        timeframe="1h",
        side=IntentSide.LONG,
        quantity=1.0,
        leverage=1.0,
        protective_exit_required=True,
    )


def _locks() -> RiskLocks:
    return RiskLocks(
        max_exposure=10.0,
        max_trades_per_day=5,
        leverage_cap=3.0,
        kill_switch=False,
        mandatory_protective_exit=True,
    )


def _risk_inputs() -> RiskInputs:
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


def _risk_config() -> GateRiskConfig:
    return GateRiskConfig(missing_red=0.2, atr_yellow=0.02, atr_red=0.05)


def test_unknown_strategy_cannot_arm() -> None:
    registry = StrategyRegistry()
    ctx = UIContext(ControlPlane(ControlPlaneState()), registry)
    with pytest.raises(ValueError, match="strategy_not_approved"):
        arm_live(ctx, "unknown")


def test_ui_cannot_execute_without_arm(tmp_path: Path) -> None:
    registry = StrategyRegistry()
    registry.register(
        StrategySpec(
            strategy_id="strat-1",
            version=1,
            name="Demo",
            description="test",
            tests_passed=True,
            changelog="init",
        )
    )
    control = ControlPlane(ControlPlaneState())
    ctx = UIContext(control, registry)

    decision = run_paper(
        ctx,
        intent=_intent(),
        risk_state=RiskState.GREEN,
        permission=Permission.ALLOW,
        risk_inputs=_risk_inputs(),
        risk_config=_risk_config(),
        locks=_locks(),
        current_exposure=0.0,
        trades_today=0,
        data_snapshot_hash="data",
        feature_snapshot_hash="features",
        strategy_id="strat-1",
        decision_path=tmp_path / "decisions.jsonl",
    )
    assert decision.action == "blocked"
    assert decision.reason == "not_armed"


def test_unapproved_strategy_blocked_even_if_armed(tmp_path: Path) -> None:
    registry = StrategyRegistry()
    control = ControlPlane(ControlPlaneState(armed=True, approved_strategies=set()))
    ctx = UIContext(control, registry)

    decision = run_paper(
        ctx,
        intent=_intent(),
        risk_state=RiskState.GREEN,
        permission=Permission.ALLOW,
        risk_inputs=_risk_inputs(),
        risk_config=_risk_config(),
        locks=_locks(),
        current_exposure=0.0,
        trades_today=0,
        data_snapshot_hash="data",
        feature_snapshot_hash="features",
        strategy_id="strat-unknown",
        decision_path=tmp_path / "decisions.jsonl",
    )
    assert decision.action == "blocked"
    assert decision.reason == "strategy_not_approved"


def test_kill_switch_blocks_paper_run(tmp_path: Path) -> None:
    registry = StrategyRegistry()
    registry.register(
        StrategySpec(
            strategy_id="strat-1",
            version=1,
            name="Demo",
            description="test",
            tests_passed=True,
            changelog="init",
        )
    )
    control = ControlPlane(
        ControlPlaneState(armed=True, approved_strategies={"strat-1"}, kill_switch=True)
    )
    ctx = UIContext(control, registry)

    decision_path = tmp_path / "decisions.jsonl"
    decision = run_paper(
        ctx,
        intent=_intent(),
        risk_state=RiskState.GREEN,
        permission=Permission.ALLOW,
        risk_inputs=_risk_inputs(),
        risk_config=_risk_config(),
        locks=_locks(),
        current_exposure=0.0,
        trades_today=0,
        data_snapshot_hash="data",
        feature_snapshot_hash="features",
        strategy_id="strat-1",
        decision_path=decision_path,
    )
    assert decision.action == "blocked"
    assert decision.reason == "kill_switch"
    assert not decision_path.exists()

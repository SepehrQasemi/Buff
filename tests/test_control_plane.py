from __future__ import annotations

from pathlib import Path

import pytest

from control_plane.core import ControlPlane, ControlPlaneState
from execution.locks import RiskLocks
from execution.types import IntentSide, OrderIntent
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

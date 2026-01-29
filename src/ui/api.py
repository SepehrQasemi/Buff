from __future__ import annotations

from pathlib import Path

from control_plane.core import ControlPlane
from execution.locks import RiskLocks
from execution.types import OrderIntent
from risk.types import Permission, RiskState
from strategies.registry import StrategyRegistry


class UIContext:
    def __init__(self, control_plane: ControlPlane, registry: StrategyRegistry) -> None:
        self.control_plane = control_plane
        self.registry = registry


def status(ctx: UIContext) -> object:
    return ctx.control_plane.status()


def arm_live(ctx: UIContext, strategy_id: str) -> None:
    ctx.control_plane.approve_strategy(ctx.registry, strategy_id)
    ctx.control_plane.arm_live(strategy_id)


def disarm_live(ctx: UIContext) -> None:
    ctx.control_plane.disarm_live()


def kill_switch(ctx: UIContext) -> None:
    ctx.control_plane.kill_switch()


def run_backtest(ctx: UIContext, *_args: object, **_kwargs: object) -> None:
    raise NotImplementedError("Backtest runner not implemented in Phase 0.")


def run_paper(
    ctx: UIContext,
    intent: OrderIntent,
    risk_state: RiskState,
    permission: Permission,
    locks: RiskLocks,
    current_exposure: float | None,
    trades_today: int | None,
    data_snapshot_hash: str,
    feature_snapshot_hash: str,
    strategy_id: str,
    decision_path: Path,
) -> object:
    return ctx.control_plane.run_paper(
        intent=intent,
        risk_state=risk_state,
        permission=permission,
        locks=locks,
        current_exposure=current_exposure,
        trades_today=trades_today,
        data_snapshot_hash=data_snapshot_hash,
        feature_snapshot_hash=feature_snapshot_hash,
        strategy_id=strategy_id,
        decision_path=decision_path,
    )

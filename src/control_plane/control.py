from __future__ import annotations

from typing import Iterable

from .state import ControlConfig, ControlState, SystemState


def arm(config: ControlConfig, approvals: Iterable[str]) -> ControlState:
    tokens = set(approvals)
    missing = config.required_approvals - tokens
    if missing:
        raise ValueError(f"missing_approvals:{sorted(missing)}")
    return ControlState(
        state=SystemState.ARMED,
        environment=config.environment,
        approvals=tokens,
        reason="armed",
    )


def disarm(reason: str) -> ControlState:
    return ControlState(state=SystemState.DISARMED, reason=reason)


def require_armed(state: ControlState) -> None:
    if state.state != SystemState.ARMED:
        raise RuntimeError("control_not_armed")


def kill_switch(state: ControlState, reason: str) -> ControlState:
    return ControlState(
        state=SystemState.DISARMED,
        environment=state.environment,
        approvals=state.approvals,
        reason=reason or "kill_switch",
    )

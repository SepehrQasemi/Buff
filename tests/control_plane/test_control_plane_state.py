from __future__ import annotations

import pytest

from control_plane.control import arm, kill_switch, require_armed
from control_plane.state import ControlConfig, ControlState, SystemState


def test_require_armed_raises() -> None:
    state = ControlState(state=SystemState.DISARMED)
    with pytest.raises(RuntimeError):
        require_armed(state)


def test_arm_requires_approvals() -> None:
    config = ControlConfig(required_approvals={"approved"})
    with pytest.raises(ValueError):
        arm(config, approvals=[])
    armed = arm(config, approvals=["approved"])
    assert armed.state == SystemState.ARMED


def test_kill_switch_disarms() -> None:
    state = ControlState(state=SystemState.ARMED)
    killed = kill_switch(state, "manual")
    assert killed.state == SystemState.DISARMED

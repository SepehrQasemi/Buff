from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SystemState(str, Enum):
    DISARMED = "DISARMED"
    ARMED = "ARMED"


class Environment(str, Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"


@dataclass(frozen=True)
class ControlConfig:
    environment: Environment = Environment.PAPER
    required_approvals: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class ControlState:
    state: SystemState = SystemState.DISARMED
    environment: Environment = Environment.PAPER
    approvals: set[str] = field(default_factory=set)
    reason: str | None = None

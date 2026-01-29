from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

from risk.types import RiskState, Permission


class PositionState(str, Enum):
    FLAT = "FLAT"
    OPENING = "OPENING"
    OPEN = "OPEN"
    CLOSING = "CLOSING"


class IntentSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


@dataclass(frozen=True)
class OrderIntent:
    event_id: str
    intent_id: str
    symbol: str
    timeframe: str
    side: IntentSide
    quantity: float
    leverage: float
    protective_exit_required: bool
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionDecision:
    risk_state: RiskState
    permission: Permission
    action: str
    reason: str
    order_ids: tuple[str, ...] = ()
    filled_qty: float = 0.0
    status: str = ""

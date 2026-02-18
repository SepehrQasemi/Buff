from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

from audit.schema import canonical_json, sha256_hex

from risk.contracts import RiskState, Permission


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

    def intent_hash(self) -> str:
        """Deterministic payload hash (excludes event_id and intent_id)."""

        payload = {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "side": self.side.value,
            "quantity": self.quantity,
            "leverage": self.leverage,
            "protective_exit_required": self.protective_exit_required,
            "metadata": dict(self.metadata),
        }
        return sha256_hex(canonical_json(payload))


@dataclass(frozen=True)
class ExecutionDecision:
    risk_state: RiskState
    permission: Permission
    action: str
    reason: str
    order_ids: tuple[str, ...] = ()
    filled_qty: float = 0.0
    status: str = ""
    size_multiplier: float = 1.0
    block_reason: str | None = None
    fundamental_risk: dict | None = None

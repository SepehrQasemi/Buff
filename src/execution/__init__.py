"""Execution core: state machine, brokers, idempotency, audit."""

from typing import TYPE_CHECKING

from .audit import DecisionRecord, DecisionWriter
from .brokers import Broker, LiveBroker, OrderResult, PaperBroker
from .locks import RiskLocks, RiskLockStatus
from .types import IntentSide, OrderIntent, PositionState

if TYPE_CHECKING:  # pragma: no cover - type check only
    from .engine import ExecutionEngine

__all__ = [
    "Broker",
    "LiveBroker",
    "OrderResult",
    "PaperBroker",
    "ExecutionEngine",
    "DecisionRecord",
    "DecisionWriter",
    "RiskLocks",
    "RiskLockStatus",
    "IntentSide",
    "OrderIntent",
    "PositionState",
]


def __getattr__(name: str):  # pragma: no cover - import shim
    if name == "ExecutionEngine":
        from .engine import ExecutionEngine

        return ExecutionEngine
    raise AttributeError(name)

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal, TypedDict

try:
    from risk.contracts import RiskState
except ImportError:  # pragma: no cover - local fallback

    class RiskState(str, Enum):
        GREEN = "GREEN"
        YELLOW = "YELLOW"
        RED = "RED"


class MarketSignals(TypedDict):
    trend_state: Literal["up", "down", "flat", "unknown"]
    volatility_regime: Literal["low", "mid", "high", "unknown"]
    momentum_state: Literal["bull", "bear", "neutral", "unknown"]
    structure_state: Literal["breakout", "meanrevert", "none", "unknown"]


@dataclass(frozen=True)
class SelectionResult:
    strategy_id: str | None
    reason: str
    rule_id: str
    inputs: dict[str, object]


__all__ = ["MarketSignals", "SelectionResult", "RiskState"]

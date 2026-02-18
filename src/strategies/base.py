from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from risk.contracts import RiskState


class StrategyEngine(Protocol):
    engine_id: str
    description: str
    required_market_keys: set[str]

    def is_applicable(self, *, market_state: dict, timeframe: str) -> tuple[bool, list[str]]: ...


@dataclass(frozen=True)
class StrategyProfile:
    strategy_id: str
    engine_id: str
    description: str
    conservative: bool
    priority: int
    required_market_keys: set[str]
    required_conditions: dict[str, object]

    def is_profile_applicable(self, *, market_state: dict) -> tuple[bool, list[str]]:
        missing = sorted(self.required_market_keys - set(market_state.keys()))
        if missing:
            return False, [f"PROFILE_MISSING_KEYS:{','.join(missing)}"]

        for key, expected in self.required_conditions.items():
            if market_state.get(key) != expected:
                return False, [f"PROFILE_CONDITION_MISMATCH:{key}"]

        return True, ["PROFILE_OK"]


class StrategySpec(Protocol):
    strategy_id: str
    name: str
    description: str
    allowed_risk_states: set[RiskState]
    tags: set[str]


@dataclass(frozen=True)
class StrategySpecImpl:
    strategy_id: str
    name: str
    description: str
    allowed_risk_states: set[RiskState]
    tags: set[str]

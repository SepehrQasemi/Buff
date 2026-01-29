from __future__ import annotations

from dataclasses import dataclass, field

from strategies.base import StrategyEngine


@dataclass(frozen=True)
class TrendEngine(StrategyEngine):
    engine_id: str = "trend"
    description: str = "Trend applicability checks"
    required_market_keys: set[str] = field(default_factory=lambda: {"trend_state"})

    def is_applicable(self, *, market_state: dict, timeframe: str) -> tuple[bool, list[str]]:
        missing = sorted(self.required_market_keys - set(market_state.keys()))
        if missing:
            return False, [f"ENGINE_MISSING_KEYS:{','.join(missing)}"]

        trend_state = market_state.get("trend_state")
        if trend_state in {"UP", "DOWN"}:
            return True, ["ENGINE_TREND_OK"]
        return False, ["ENGINE_TREND_NOT_APPLICABLE"]

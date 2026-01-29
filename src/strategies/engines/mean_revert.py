from __future__ import annotations

from dataclasses import dataclass, field

from strategies.base import StrategyEngine


@dataclass(frozen=True)
class MeanRevertEngine(StrategyEngine):
    engine_id: str = "mean_revert"
    description: str = "Mean reversion applicability checks"
    required_market_keys: set[str] = field(default_factory=lambda: {"trend_state"})

    def is_applicable(self, *, market_state: dict, timeframe: str) -> tuple[bool, list[str]]:
        missing = sorted(self.required_market_keys - set(market_state.keys()))
        if missing:
            return False, [f"ENGINE_MISSING_KEYS:{','.join(missing)}"]

        trend_state = market_state.get("trend_state")
        if trend_state == "RANGE":
            return True, ["ENGINE_MEAN_REVERT_OK"]
        return False, ["ENGINE_MEAN_REVERT_NOT_APPLICABLE"]

from __future__ import annotations

from dataclasses import dataclass, field

from strategies.base import StrategyEngine


@dataclass(frozen=True)
class BreakoutEngine(StrategyEngine):
    engine_id: str = "breakout"
    description: str = "Breakout applicability checks"
    required_market_keys: set[str] = field(default_factory=lambda: {"volatility_regime"})

    def is_applicable(self, *, market_state: dict, timeframe: str) -> tuple[bool, list[str]]:
        missing = sorted(self.required_market_keys - set(market_state.keys()))
        if missing:
            return False, [f"ENGINE_MISSING_KEYS:{','.join(missing)}"]

        volatility_regime = market_state.get("volatility_regime")
        momentum_state = market_state.get("momentum_state")
        if volatility_regime in {"HIGH", "EXPANDING"} or momentum_state == "SPIKE":
            return True, ["ENGINE_BREAKOUT_OK"]
        return False, ["ENGINE_BREAKOUT_NOT_APPLICABLE"]

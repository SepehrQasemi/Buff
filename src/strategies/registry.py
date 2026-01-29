from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    version: int
    name: str
    description: str
    tests_passed: bool
    changelog: str


@dataclass
class StrategyRegistry:
    strategies: dict[str, StrategySpec] = field(default_factory=dict)

    def register(self, spec: StrategySpec) -> None:
        existing = self.strategies.get(spec.strategy_id)
        if existing is not None and spec.version <= existing.version:
            raise ValueError("strategy_version_not_incremented")
        self.strategies[spec.strategy_id] = spec

    def is_registered(self, strategy_id: str) -> bool:
        return strategy_id in self.strategies

    def is_approved(self, strategy_id: str) -> bool:
        spec = self.strategies.get(strategy_id)
        if spec is None:
            return False
        return spec.tests_passed

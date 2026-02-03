from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from strategy_registry.decision import DECISION_SCHEMA_VERSION, Decision


class StrategyRegistryError(ValueError):
    """Raised when strategy registry constraints are violated."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class StrategyId:
    name: str
    version: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise StrategyRegistryError("strategy_id_invalid")
        if not isinstance(self.version, str) or not self.version:
            raise StrategyRegistryError("strategy_version_invalid")

    def key(self) -> str:
        return f"{self.name}@{self.version}"


@dataclass(frozen=True)
class StrategySpec:
    name: str
    version: str
    description: str
    required_features: Sequence[str]
    required_timeframes: Sequence[str] = field(default_factory=lambda: ("1m",))
    params: Mapping[str, Any] = field(default_factory=dict)
    decision_schema_version: int = DECISION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise StrategyRegistryError("strategy_name_invalid")
        if not isinstance(self.version, str) or not self.version:
            raise StrategyRegistryError("strategy_version_invalid")
        if not isinstance(self.description, str) or not self.description:
            raise StrategyRegistryError("strategy_description_invalid")

        features = tuple(self.required_features or ())
        for value in features:
            if not isinstance(value, str) or not value:
                raise StrategyRegistryError("strategy_required_features_invalid")

        timeframes = tuple(self.required_timeframes or ())
        for value in timeframes:
            if not isinstance(value, str) or not value:
                raise StrategyRegistryError("strategy_required_timeframes_invalid")

        params = dict(self.params or {})
        for key in params.keys():
            if not isinstance(key, str):
                raise StrategyRegistryError("strategy_params_invalid")

        if self.decision_schema_version != DECISION_SCHEMA_VERSION:
            raise StrategyRegistryError("strategy_decision_schema_invalid")

        object.__setattr__(self, "required_features", features)
        object.__setattr__(self, "required_timeframes", timeframes)
        object.__setattr__(self, "params", params)

    @property
    def strategy_id(self) -> StrategyId:
        return StrategyId(name=self.name, version=self.version)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "required_features": list(self.required_features),
            "required_timeframes": list(self.required_timeframes),
            "params": dict(self.params),
            "decision_schema_version": self.decision_schema_version,
        }


class Strategy(Protocol):
    spec: StrategySpec

    def run(self, features_df: Any, metadata: Any, as_of_utc: str) -> Decision: ...


@dataclass(frozen=True)
class StrategyDefinition:
    spec: StrategySpec
    runner: Any

    def run(self, features_df: Any, metadata: Any, as_of_utc: str) -> Decision:
        return self.runner(features_df, metadata, as_of_utc)


@dataclass
class StrategyRegistry:
    strategies: dict[str, Strategy] = field(default_factory=dict)

    def register(self, strategy: Strategy) -> None:
        if not isinstance(strategy, StrategyDefinition) and not hasattr(strategy, "spec"):
            raise StrategyRegistryError("strategy_invalid")
        spec = strategy.spec
        key = spec.strategy_id.key()
        if key in self.strategies:
            raise StrategyRegistryError("strategy_already_registered")
        self.strategies[key] = strategy

    def list_strategies(self) -> list[StrategySpec]:
        specs = [strategy.spec for strategy in self.strategies.values()]
        return sorted(specs, key=lambda item: (item.name, item.version))

    def get(self, strategy_id: StrategyId | str) -> Strategy:
        key = strategy_id if isinstance(strategy_id, str) else strategy_id.key()
        strategy = self.strategies.get(key)
        if strategy is None:
            raise StrategyRegistryError("strategy_not_found")
        return strategy

    def is_registered(self, strategy_id: StrategyId | str) -> bool:
        key = strategy_id if isinstance(strategy_id, str) else strategy_id.key()
        return key in self.strategies


_DEFAULT_REGISTRY = StrategyRegistry()


def register_strategy(strategy: Strategy) -> None:
    _DEFAULT_REGISTRY.register(strategy)


def list_strategies() -> list[StrategySpec]:
    return _DEFAULT_REGISTRY.list_strategies()


def get_strategy(strategy_id: StrategyId | str) -> Strategy:
    return _DEFAULT_REGISTRY.get(strategy_id)


def _reset_registry() -> None:
    _DEFAULT_REGISTRY.strategies.clear()

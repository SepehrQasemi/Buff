from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategySpec:
    name: str
    version: str
    description: str
    required_features: list[str]


_REGISTRY: list[StrategySpec] = []


def register_strategy(spec: StrategySpec) -> None:
    if any(item.name == spec.name and item.version == spec.version for item in _REGISTRY):
        raise ValueError("strategy_already_registered")
    _REGISTRY.append(spec)


def list_strategies() -> list[StrategySpec]:
    return sorted(_REGISTRY, key=lambda item: (item.name, item.version))


def get_strategy(name: str) -> StrategySpec:
    matches = [item for item in _REGISTRY if item.name == name]
    if not matches:
        raise ValueError("strategy_not_found")
    if len(matches) > 1:
        raise ValueError("strategy_name_ambiguous")
    return matches[0]


def _reset_registry() -> None:
    _REGISTRY.clear()

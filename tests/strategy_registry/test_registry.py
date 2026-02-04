from __future__ import annotations

import pytest

from strategy_registry.registry import (
    StrategyDefinition,
    StrategySpec,
    StrategyRegistry,
    StrategyRegistryError,
)


def _definition(name: str, version: str) -> StrategyDefinition:
    spec = StrategySpec(
        name=name,
        version=version,
        description=f"{name} strategy",
        required_features=["ema_20@1"],
        required_timeframes=["1m"],
        params={"alpha": 1},
    )

    def _runner(features_df, metadata, as_of_utc):  # pragma: no cover - not used
        raise AssertionError("runner_not_called")

    return StrategyDefinition(spec=spec, runner=_runner)


def test_registry_deterministic_order() -> None:
    registry = StrategyRegistry()
    registry.register(_definition("beta", "1.0.0"))
    registry.register(_definition("alpha", "1.0.0"))
    names = [spec.name for spec in registry.list_strategies()]
    assert names == ["alpha", "beta"]


def test_duplicate_id_rejected() -> None:
    registry = StrategyRegistry()
    registry.register(_definition("alpha", "1.0.0"))
    with pytest.raises(StrategyRegistryError):
        registry.register(_definition("alpha", "1.0.0"))


def test_get_strategy_by_id() -> None:
    registry = StrategyRegistry()
    definition = _definition("alpha", "1.0.0")
    registry.register(definition)
    strategy = registry.get("alpha@1.0.0")
    assert strategy.spec.name == "alpha"

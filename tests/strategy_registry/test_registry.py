from __future__ import annotations

import pytest

from strategy_registry.registry import (
    StrategyDefinition,
    StrategySpec,
    StrategyRegistryError,
    _reset_registry,
    get_strategy,
    list_strategies,
    register_strategy,
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
    _reset_registry()
    register_strategy(_definition("beta", "1.0.0"))
    register_strategy(_definition("alpha", "1.0.0"))
    names = [spec.name for spec in list_strategies()]
    assert names == ["alpha", "beta"]


def test_duplicate_id_rejected() -> None:
    _reset_registry()
    register_strategy(_definition("alpha", "1.0.0"))
    with pytest.raises(StrategyRegistryError):
        register_strategy(_definition("alpha", "1.0.0"))


def test_get_strategy_by_id() -> None:
    _reset_registry()
    definition = _definition("alpha", "1.0.0")
    register_strategy(definition)
    strategy = get_strategy("alpha@1.0.0")
    assert strategy.spec.name == "alpha"

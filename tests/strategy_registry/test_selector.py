from __future__ import annotations

import pytest

from strategy_registry.registry import StrategyDefinition, StrategyRegistry, StrategySpec
from strategy_registry.selector import SelectorConfig, SelectorError, select_strategy


def _registry() -> StrategyRegistry:
    registry = StrategyRegistry()

    def _runner(features_df, metadata, as_of_utc):  # pragma: no cover - selector only
        raise AssertionError("runner_not_called")

    registry.register(
        StrategyDefinition(
            spec=StrategySpec(
                name="trend",
                version="1.0.0",
                description="trend",
                required_features=["ema_20@1"],
                required_timeframes=["1m"],
                params={},
            ),
            runner=_runner,
        )
    )
    registry.register(
        StrategyDefinition(
            spec=StrategySpec(
                name="mean_revert",
                version="1.0.0",
                description="mean",
                required_features=["rsi_14@1"],
                required_timeframes=["1m"],
                params={},
            ),
            runner=_runner,
        )
    )
    return registry


def test_selector_fixed_strategy_deterministic() -> None:
    registry = _registry()
    config = SelectorConfig(
        schema_version=1,
        allowed_strategy_ids=["trend@1.0.0", "mean_revert@1.0.0"],
        mode="fixed",
        fixed_strategy_id="trend@1.0.0",
    )
    record_a = select_strategy(config, market_state={}, registry=registry)
    record_b = select_strategy(config, market_state={}, registry=registry)
    assert record_a.to_dict() == record_b.to_dict()
    assert record_a.chosen_strategy_id == "trend@1.0.0"


def test_selector_regime_rule() -> None:
    registry = _registry()
    config = SelectorConfig(
        schema_version=1,
        allowed_strategy_ids=["trend@1.0.0", "mean_revert@1.0.0"],
        mode="regime",
        regime_map={"trend": "trend@1.0.0", "range": "mean_revert@1.0.0"},
    )
    record = select_strategy(config, market_state={"regime_id": "range"}, registry=registry)
    assert record.chosen_strategy_id == "mean_revert@1.0.0"


def test_selector_missing_features_fail_closed() -> None:
    registry = _registry()
    config = SelectorConfig(
        schema_version=1,
        allowed_strategy_ids=["trend@1.0.0"],
        mode="fixed",
        fixed_strategy_id="trend@1.0.0",
    )
    metadata = {"features": [{"feature_id": "rsi_14", "version": 1}]}
    with pytest.raises(SelectorError):
        select_strategy(config, market_state={}, registry=registry, metadata=metadata)

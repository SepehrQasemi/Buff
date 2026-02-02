from __future__ import annotations

import pytest

from strategies.registry import StrategyRegistry, StrategySpec


def _spec(strategy_id: str, version: int, tests_passed: bool = True) -> StrategySpec:
    return StrategySpec(
        strategy_id=strategy_id,
        version=version,
        name=f"Name {strategy_id}",
        description="desc",
        tests_passed=tests_passed,
        changelog="init",
    )


def test_list_is_deterministic_sorted() -> None:
    registry = StrategyRegistry()
    registry.register(_spec("b", 2))
    registry.register(_spec("a", 1))
    registry.register(_spec("b", 3))

    listed = registry.list()
    assert [spec.strategy_id for spec in listed] == ["a", "b"]
    assert [spec.version for spec in listed] == [1, 3]


def test_validate_rejects_duplicate_id_version() -> None:
    registry = StrategyRegistry()
    first = _spec("dup", 1)
    second = _spec("dup", 1)
    registry.strategies["one"] = first
    registry.strategies["two"] = second

    with pytest.raises(ValueError, match="duplicate_strategy_version"):
        registry.validate()


def test_validate_rejects_tests_not_passed() -> None:
    registry = StrategyRegistry()
    registry.register(_spec("a", 1, tests_passed=False))

    with pytest.raises(ValueError, match="tests_not_passed"):
        registry.validate()

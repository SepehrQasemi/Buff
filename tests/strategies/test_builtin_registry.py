from __future__ import annotations

from strategies.builtins.common import is_semver
from strategies.registry import get_strategy, list_strategies


def test_builtin_registry_count_and_ids() -> None:
    strategies = list_strategies()
    assert len(strategies) == 20
    ids = [schema["id"] for schema in strategies]
    assert len(ids) == len(set(ids))


def test_builtin_registry_versions_semver() -> None:
    for schema in list_strategies():
        assert is_semver(schema["version"])


def test_get_strategy_by_id_version() -> None:
    strategies = list_strategies()
    target = strategies[0]
    strategy = get_strategy(f"{target['id']}@{target['version']}")
    schema = strategy.get_schema()
    assert schema["id"] == target["id"]
    assert schema["version"] == target["version"]

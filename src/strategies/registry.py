from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping

from strategies.base import StrategyEngine, StrategyProfile
from strategies.engines import BreakoutEngine, MeanRevertEngine, TrendEngine


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

    def list(self) -> list[StrategySpec]:
        return sorted(
            self.strategies.values(),
            key=lambda spec: (spec.strategy_id, spec.version),
        )

    def validate(self) -> None:
        specs = list(self.strategies.values())
        seen: set[tuple[str, int]] = set()
        for spec in sorted(specs, key=lambda item: (item.strategy_id, item.version)):
            if not isinstance(spec.strategy_id, str) or not spec.strategy_id:
                raise ValueError("invalid_strategy_id")
            if not isinstance(spec.version, int) or isinstance(spec.version, bool):
                raise ValueError("invalid_strategy_version")
            if not isinstance(spec.name, str) or not spec.name:
                raise ValueError("invalid_strategy_name")
            if not isinstance(spec.description, str):
                raise ValueError("invalid_strategy_description")
            if not isinstance(spec.tests_passed, bool):
                raise ValueError("invalid_tests_passed")
            if not spec.tests_passed:
                raise ValueError("tests_not_passed")
            if not isinstance(spec.changelog, str):
                raise ValueError("invalid_changelog")
            key = (spec.strategy_id, spec.version)
            if key in seen:
                raise ValueError("duplicate_strategy_version")
            seen.add(key)

    def is_registered(self, strategy_id: str) -> bool:
        return strategy_id in self.strategies

    def is_approved(self, strategy_id: str) -> bool:
        spec = self.strategies.get(strategy_id)
        if spec is None:
            return False
        return spec.tests_passed


def build_engines() -> dict[str, StrategyEngine]:
    engines = {
        "trend": TrendEngine(),
        "mean_revert": MeanRevertEngine(),
        "breakout": BreakoutEngine(),
    }
    return engines


def build_profiles() -> list[StrategyProfile]:
    return [
        StrategyProfile(
            strategy_id="TREND_FOLLOW_V1",
            engine_id="trend",
            description="Trend follow V1 profile",
            conservative=False,
            priority=15,
            required_market_keys={"trend_state", "structure_state"},
            required_conditions={"trend_state": "UP", "structure_state": "BREAKOUT"},
        ),
        StrategyProfile(
            strategy_id="trend_follow_v1_conservative",
            engine_id="trend",
            description="Trend follow up, conservative",
            conservative=True,
            priority=10,
            required_market_keys={"trend_state"},
            required_conditions={"trend_state": "UP"},
        ),
        StrategyProfile(
            strategy_id="MEAN_REVERT_V1",
            engine_id="mean_revert",
            description="Mean revert V1 profile",
            conservative=True,
            priority=55,
            required_market_keys={"trend_state", "structure_state"},
            required_conditions={"trend_state": "RANGE", "structure_state": "MEANREVERT"},
        ),
        StrategyProfile(
            strategy_id="trend_follow_v1_short",
            engine_id="trend",
            description="Trend follow down",
            conservative=False,
            priority=20,
            required_market_keys={"trend_state"},
            required_conditions={"trend_state": "DOWN"},
        ),
        StrategyProfile(
            strategy_id="trend_follow_v1_high_vol",
            engine_id="trend",
            description="Trend follow high volatility",
            conservative=False,
            priority=30,
            required_market_keys={"trend_state", "volatility_regime"},
            required_conditions={"volatility_regime": "HIGH"},
        ),
        StrategyProfile(
            strategy_id="trend_follow_v1_low_vol",
            engine_id="trend",
            description="Trend follow low volatility",
            conservative=True,
            priority=40,
            required_market_keys={"trend_state", "volatility_regime"},
            required_conditions={"volatility_regime": "LOW"},
        ),
        StrategyProfile(
            strategy_id="mean_revert_v1_range",
            engine_id="mean_revert",
            description="Mean reversion range",
            conservative=True,
            priority=50,
            required_market_keys={"trend_state"},
            required_conditions={"trend_state": "RANGE"},
        ),
        StrategyProfile(
            strategy_id="mean_revert_v1_low_vol",
            engine_id="mean_revert",
            description="Mean reversion low volatility",
            conservative=True,
            priority=60,
            required_market_keys={"trend_state", "volatility_regime"},
            required_conditions={"trend_state": "RANGE", "volatility_regime": "LOW"},
        ),
        StrategyProfile(
            strategy_id="mean_revert_v1_strict",
            engine_id="mean_revert",
            description="Mean reversion strict range",
            conservative=False,
            priority=70,
            required_market_keys={"trend_state", "range_state"},
            required_conditions={"trend_state": "RANGE", "range_state": "TIGHT"},
        ),
        StrategyProfile(
            strategy_id="breakout_v1_normal",
            engine_id="breakout",
            description="Breakout expanding volatility",
            conservative=False,
            priority=80,
            required_market_keys={"volatility_regime"},
            required_conditions={"volatility_regime": "EXPANDING"},
        ),
        StrategyProfile(
            strategy_id="breakout_v1_high_vol",
            engine_id="breakout",
            description="Breakout high volatility",
            conservative=False,
            priority=90,
            required_market_keys={"volatility_regime"},
            required_conditions={"volatility_regime": "HIGH"},
        ),
        StrategyProfile(
            strategy_id="breakout_v1_spike",
            engine_id="breakout",
            description="Breakout momentum spike",
            conservative=False,
            priority=100,
            required_market_keys={"momentum_state"},
            required_conditions={"momentum_state": "SPIKE"},
        ),
    ]


def get_profiles() -> list[StrategyProfile]:
    profiles = build_profiles()
    return sorted(profiles, key=lambda profile: (profile.priority, profile.strategy_id))


def get_profile(strategy_id: str) -> StrategyProfile | None:
    for profile in build_profiles():
        if profile.strategy_id == strategy_id:
            return profile
    return None


_BUILTIN_REGISTRY: dict[str, object] | None = None
_BUILTIN_SCHEMAS: list[dict[str, Any]] | None = None


def _validate_param_schema(param: Mapping[str, Any]) -> None:
    name = param.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("strategy_schema_invalid")
    param_type = param.get("type")
    if param_type not in {"int", "float", "bool", "string", "enum"}:
        raise ValueError("strategy_schema_invalid")
    if "default" not in param:
        raise ValueError("strategy_schema_invalid")
    if "enum" in param:
        enum = param.get("enum")
        if enum is not None and not isinstance(enum, list):
            raise ValueError("strategy_schema_invalid")


def _validate_builtin_schema(schema: Mapping[str, Any], strategy_id: str, version: str) -> None:
    required = {
        "id",
        "name",
        "version",
        "category",
        "description",
        "warmup_bars",
        "params",
        "inputs",
        "outputs",
    }
    if not required.issubset(schema.keys()):
        raise ValueError("strategy_schema_invalid")
    if schema.get("id") != strategy_id:
        raise ValueError("strategy_schema_invalid")
    if schema.get("version") != version:
        raise ValueError("strategy_schema_invalid")
    if not isinstance(schema.get("name"), str) or not schema.get("name"):
        raise ValueError("strategy_schema_invalid")
    if not isinstance(schema.get("description"), str):
        raise ValueError("strategy_schema_invalid")
    warmup = schema.get("warmup_bars")
    if not isinstance(warmup, int) or isinstance(warmup, bool) or warmup < 0:
        raise ValueError("strategy_schema_invalid")

    from strategies.builtins.common import ALLOWED_CATEGORIES, ALLOWED_INTENTS, is_semver

    if not is_semver(str(schema.get("version", ""))):
        raise ValueError("strategy_schema_invalid")
    if schema.get("category") not in ALLOWED_CATEGORIES:
        raise ValueError("strategy_schema_invalid")

    params = schema.get("params")
    if not isinstance(params, list):
        raise ValueError("strategy_schema_invalid")
    for param in params:
        if not isinstance(param, Mapping):
            raise ValueError("strategy_schema_invalid")
        _validate_param_schema(param)

    inputs = schema.get("inputs")
    if not isinstance(inputs, Mapping):
        raise ValueError("strategy_schema_invalid")
    series = inputs.get("series")
    if not isinstance(series, list) or not all(isinstance(item, str) and item for item in series):
        raise ValueError("strategy_schema_invalid")

    outputs = schema.get("outputs")
    if not isinstance(outputs, Mapping):
        raise ValueError("strategy_schema_invalid")
    intents = outputs.get("intents")
    if not isinstance(intents, list) or not ALLOWED_INTENTS.issubset(set(intents)):
        raise ValueError("strategy_schema_invalid")
    if not isinstance(outputs.get("provides_confidence"), bool):
        raise ValueError("strategy_schema_invalid")
    if not isinstance(outputs.get("provides_tags"), bool):
        raise ValueError("strategy_schema_invalid")


def _ensure_builtin_registry() -> None:
    global _BUILTIN_REGISTRY, _BUILTIN_SCHEMAS
    if _BUILTIN_REGISTRY is not None:
        return
    from strategies.builtins import BUILTIN_STRATEGIES

    registry: dict[str, object] = {}
    schemas: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for definition in BUILTIN_STRATEGIES:
        schema = definition.get_schema()
        if not isinstance(schema, Mapping):
            raise ValueError("strategy_schema_invalid")
        strategy_id = str(schema.get("id", ""))
        version = str(schema.get("version", ""))
        _validate_builtin_schema(schema, strategy_id, version)
        key = f"{strategy_id}@{version}"
        if key in registry:
            raise ValueError("strategy_duplicate_id")
        if strategy_id in seen_ids:
            raise ValueError("strategy_duplicate_id")
        registry[key] = definition
        seen_ids.add(strategy_id)
        schemas.append(dict(schema))

    schemas.sort(key=lambda item: (str(item.get("id", "")), str(item.get("version", ""))))
    _BUILTIN_REGISTRY = registry
    _BUILTIN_SCHEMAS = schemas


def list_strategies() -> list[dict[str, Any]]:
    _ensure_builtin_registry()
    assert _BUILTIN_SCHEMAS is not None
    return copy.deepcopy(_BUILTIN_SCHEMAS)


def get_strategy(strategy_id_version: str):
    if not isinstance(strategy_id_version, str) or "@" not in strategy_id_version:
        raise ValueError("strategy_id_invalid")
    _ensure_builtin_registry()
    assert _BUILTIN_REGISTRY is not None
    strategy = _BUILTIN_REGISTRY.get(strategy_id_version)
    if strategy is None:
        raise ValueError("strategy_not_found")
    return strategy

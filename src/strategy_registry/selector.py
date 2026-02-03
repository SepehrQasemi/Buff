from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from strategy_registry.registry import StrategyRegistry, StrategyRegistryError


class SelectorError(ValueError):
    """Raised when selector contract is violated."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SelectorConfig:
    schema_version: int
    allowed_strategy_ids: Sequence[str]
    mode: str
    fixed_strategy_id: str | None = None
    regime_map: Mapping[str, str] | None = None
    default_strategy_id: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise SelectorError("selector_schema_invalid")
        if self.mode not in {"fixed", "regime"}:
            raise SelectorError("selector_mode_invalid")
        allowed = tuple(self.allowed_strategy_ids or ())
        for value in allowed:
            if not isinstance(value, str) or not value:
                raise SelectorError("selector_allowed_invalid")
        if self.mode == "fixed" and (
            not isinstance(self.fixed_strategy_id, str) or not self.fixed_strategy_id
        ):
            raise SelectorError("selector_fixed_invalid")
        if self.regime_map is not None and not isinstance(self.regime_map, Mapping):
            raise SelectorError("selector_regime_map_invalid")

    def ordered_allowed(self) -> list[str]:
        return sorted(set(self.allowed_strategy_ids))


@dataclass(frozen=True)
class SelectionRecord:
    schema_version: int
    chosen_strategy_id: str | None
    chosen_strategy_version: str | None
    reason_codes: Sequence[str]
    audit_fields: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "chosen_strategy_id": self.chosen_strategy_id,
            "chosen_strategy_version": self.chosen_strategy_version,
            "reason_codes": list(self.reason_codes),
            "audit_fields": dict(self.audit_fields),
        }


def _resolve_strategy_version(strategy_id: str, registry: StrategyRegistry) -> str:
    strategy = registry.get(strategy_id)
    return strategy.spec.version


def _select_from_regime(config: SelectorConfig, regime_id: str) -> str | None:
    if config.regime_map is None:
        return config.default_strategy_id
    if regime_id in config.regime_map:
        return config.regime_map[regime_id]
    return config.default_strategy_id


def _available_features(metadata: Mapping[str, Any] | None) -> set[str] | None:
    if metadata is None:
        return None
    features = metadata.get("features")
    if not isinstance(features, list):
        raise SelectorError("selector_metadata_invalid")
    ids = set()
    for spec in features:
        if not isinstance(spec, Mapping):
            raise SelectorError("selector_metadata_invalid")
        feature_id = spec.get("feature_id")
        version = spec.get("version")
        if not isinstance(feature_id, str) or not feature_id:
            raise SelectorError("selector_metadata_invalid")
        if not isinstance(version, (int, str)) or isinstance(version, bool):
            raise SelectorError("selector_metadata_invalid")
        ids.add(f"{feature_id}@{version}")
    return ids


def select_strategy(
    config: SelectorConfig,
    *,
    market_state: Mapping[str, Any],
    registry: StrategyRegistry,
    metadata: Mapping[str, Any] | None = None,
) -> SelectionRecord:
    allowed = config.ordered_allowed()
    if not allowed:
        return SelectionRecord(
            schema_version=1,
            chosen_strategy_id=None,
            chosen_strategy_version=None,
            reason_codes=["no_allowed_strategies"],
            audit_fields={"allowed_strategy_ids": [], "mode": config.mode},
        )

    for strategy_id in allowed:
        if not registry.is_registered(strategy_id):
            raise StrategyRegistryError("strategy_not_found")

    if config.mode == "fixed":
        chosen_id = config.fixed_strategy_id
        reason = "fixed_strategy"
    else:
        regime_id = str(market_state.get("regime_id", "unknown"))
        chosen_id = _select_from_regime(config, regime_id)
        reason = "regime_map" if chosen_id else "no_regime_match"

    if chosen_id is None:
        return SelectionRecord(
            schema_version=1,
            chosen_strategy_id=None,
            chosen_strategy_version=None,
            reason_codes=[reason],
            audit_fields={"allowed_strategy_ids": allowed, "mode": config.mode},
        )

    if chosen_id not in allowed:
        raise SelectorError("selector_strategy_disallowed")

    available_features = _available_features(metadata)
    if available_features is not None:
        required = registry.get(chosen_id).spec.required_features
        missing = [feat for feat in required if feat not in available_features]
        if missing:
            raise SelectorError("selector_missing_features")

    version = _resolve_strategy_version(chosen_id, registry)
    return SelectionRecord(
        schema_version=1,
        chosen_strategy_id=chosen_id,
        chosen_strategy_version=version,
        reason_codes=[reason],
        audit_fields={
            "allowed_strategy_ids": allowed,
            "mode": config.mode,
            "market_state": dict(market_state),
        },
    )

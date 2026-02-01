"""Load and validate regime rules from YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from buff.features.registry import FEATURES
from buff.regimes.errors import RegimeSchemaError
from buff.regimes.schema import RegimeSchema
from buff.regimes.types import RegimeConfig, RegimeRule


def load_regime_config(path: Path) -> RegimeConfig:
    payload = _read_yaml(path)
    try:
        schema = RegimeSchema.model_validate(payload)
    except ValidationError as exc:
        raise RegimeSchemaError(f"schema_validation_failed: {exc}") from exc
    return _normalize_schema(schema)


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RegimeSchemaError(f"schema_not_found:{path}")
    raw = path.read_text(encoding="utf-8")
    payload = yaml.safe_load(raw)
    if not isinstance(payload, dict):
        raise RegimeSchemaError("schema_root_invalid")
    return payload


def _normalize_schema(schema: RegimeSchema) -> RegimeConfig:
    if schema.schema_version != "1":
        raise RegimeSchemaError("schema_version_unsupported")

    if not schema.regimes:
        raise RegimeSchemaError("regimes_missing")

    regime_ids = [regime.regime_id for regime in schema.regimes]
    if len(set(regime_ids)) != len(regime_ids):
        raise RegimeSchemaError("regime_id_not_unique")

    priorities = [regime.priority for regime in schema.regimes]
    if len(set(priorities)) != len(priorities):
        raise RegimeSchemaError("priority_not_unique")
    if priorities != sorted(priorities, reverse=True):
        raise RegimeSchemaError("priority_order_invalid")

    if schema.regimes[0].regime_id != "RISK_OFF":
        raise RegimeSchemaError("risk_off_not_first")
    if schema.regimes[0].priority != max(priorities):
        raise RegimeSchemaError("risk_off_not_highest_priority")

    neutral = [regime for regime in schema.regimes if regime.regime_id == "NEUTRAL"]
    if len(neutral) != 1:
        raise RegimeSchemaError("neutral_missing")
    if schema.regimes[-1].regime_id != "NEUTRAL":
        raise RegimeSchemaError("neutral_not_last")
    if neutral[0].conditions is not None:
        raise RegimeSchemaError("neutral_conditions_not_allowed")
    if neutral[0].priority != min(priorities):
        raise RegimeSchemaError("neutral_not_lowest_priority")

    for regime in schema.regimes:
        if regime.regime_id != "NEUTRAL" and regime.conditions is None:
            raise RegimeSchemaError(f"conditions_required:{regime.regime_id}")
        _ensure_unique_list(regime.allowed_strategy_families, "allowed_strategy_families")
        _ensure_unique_list(regime.forbidden_strategy_families, "forbidden_strategy_families")

    feature_aliases, alias_to_canonical = _build_alias_maps(schema)
    known_features = _known_feature_names()
    referenced = _collect_referenced_features(schema)
    for feature in referenced:
        if feature in known_features:
            continue
        if feature in feature_aliases:
            continue
        if feature in alias_to_canonical:
            continue
        raise RegimeSchemaError(f"unknown_feature:{feature}")

    regimes = tuple(
        RegimeRule(
            regime_id=regime.regime_id,
            description=regime.description,
            priority=regime.priority,
            conditions=regime.conditions,
            allowed_strategy_families=tuple(regime.allowed_strategy_families),
            forbidden_strategy_families=tuple(regime.forbidden_strategy_families),
            risk_modifiers=dict(regime.risk_modifiers),
            rationale=tuple(regime.rationale),
        )
        for regime in schema.regimes
    )

    return RegimeConfig(
        schema_version=schema.schema_version,
        regimes=regimes,
        required_features=frozenset(referenced),
        feature_aliases=feature_aliases,
        alias_to_canonical=alias_to_canonical,
    )


def _known_feature_names() -> set[str]:
    outputs: set[str] = set()
    for spec in FEATURES.values():
        for out in spec["outputs"]:
            outputs.add(out)
    outputs.update({"atr_pct", "realized_vol", "realized_vol_20"})
    return outputs


def _collect_referenced_features(schema: RegimeSchema) -> set[str]:
    features: set[str] = set()
    for regime in schema.regimes:
        if regime.conditions is None:
            continue
        for name in regime.conditions.iter_features():
            features.add(name)
    return features


def _build_alias_maps(schema: RegimeSchema) -> tuple[dict[str, tuple[str, ...]], dict[str, str]]:
    feature_aliases: dict[str, tuple[str, ...]] = {}
    alias_to_canonical: dict[str, str] = {}
    for entry in schema.feature_catalog:
        if entry.name in feature_aliases or entry.name in alias_to_canonical:
            raise RegimeSchemaError("feature_catalog_duplicate")
        aliases = tuple(alias for alias in entry.aliases if alias)
        feature_aliases[entry.name] = aliases
        for alias in aliases:
            if alias in alias_to_canonical or alias in feature_aliases:
                raise RegimeSchemaError("feature_catalog_alias_duplicate")
            alias_to_canonical[alias] = entry.name
    return feature_aliases, alias_to_canonical


def _ensure_unique_list(values: list[str], field_name: str) -> None:
    if len(set(values)) != len(values):
        raise RegimeSchemaError(f"{field_name}_not_unique")

"""Pydantic schema for regime rules."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FeatureCatalogEntry(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None

    model_config = ConfigDict(extra="forbid")


class Condition(BaseModel):
    op: str
    items: list["Condition"] = Field(default_factory=list)
    feature: str | None = None
    value: float | None = None
    lower: float | None = None
    upper: float | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _parse(cls, value: Any) -> Any:
        if not isinstance(value, dict) or len(value) != 1:
            raise ValueError("condition_invalid")
        op, payload = next(iter(value.items()))
        if op in {"all", "any"}:
            if not isinstance(payload, list) or not payload:
                raise ValueError("condition_list_required")
            return {"op": op, "items": payload}
        if op == "not":
            if not isinstance(payload, dict):
                raise ValueError("condition_not_requires_object")
            return {"op": op, "items": [payload]}
        if op in {"gt", "gte", "lt", "lte", "abs_gt"}:
            feature, numeric = _parse_feature_numeric(payload)
            return {"op": op, "feature": feature, "value": numeric}
        if op == "between":
            feature, bounds = _parse_feature_bounds(payload)
            return {"op": op, "feature": feature, "lower": bounds[0], "upper": bounds[1]}
        raise ValueError(f"condition_operator_unknown:{op}")

    def iter_features(self) -> list[str]:
        if self.feature:
            return [self.feature]
        features: list[str] = []
        for item in self.items:
            features.extend(item.iter_features())
        return features


class RegimeDefinition(BaseModel):
    regime_id: str
    description: str
    priority: int
    conditions: Condition | None = None
    allowed_strategy_families: list[str]
    forbidden_strategy_families: list[str]
    risk_modifiers: dict[str, Any] = Field(default_factory=dict)
    rationale: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class RegimeSchema(BaseModel):
    schema_version: str
    regimes: list[RegimeDefinition]
    feature_catalog: list[FeatureCatalogEntry] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


def _parse_feature_numeric(payload: Any) -> tuple[str, float]:
    if not isinstance(payload, dict) or len(payload) != 1:
        raise ValueError("condition_numeric_invalid")
    feature, numeric = next(iter(payload.items()))
    if not isinstance(feature, str) or not feature:
        raise ValueError("condition_feature_invalid")
    if isinstance(numeric, bool) or not isinstance(numeric, (int, float)):
        raise ValueError("condition_numeric_invalid")
    return feature, float(numeric)


def _parse_feature_bounds(payload: Any) -> tuple[str, tuple[float, float]]:
    if not isinstance(payload, dict) or len(payload) != 1:
        raise ValueError("condition_between_invalid")
    feature, bounds = next(iter(payload.items()))
    if not isinstance(feature, str) or not feature:
        raise ValueError("condition_feature_invalid")
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
        raise ValueError("condition_between_bounds_invalid")
    lower, upper = bounds[0], bounds[1]
    if isinstance(lower, bool) or not isinstance(lower, (int, float)):
        raise ValueError("condition_between_bounds_invalid")
    if isinstance(upper, bool) or not isinstance(upper, (int, float)):
        raise ValueError("condition_between_bounds_invalid")
    lower_f = float(lower)
    upper_f = float(upper)
    if lower_f > upper_f:
        raise ValueError("condition_between_bounds_invalid")
    return feature, (lower_f, upper_f)

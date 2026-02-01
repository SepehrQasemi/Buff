"""Types for regime semantics outputs and configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from buff.regimes.schema import Condition


@dataclass(frozen=True)
class RegimeRule:
    regime_id: str
    description: str
    priority: int
    conditions: Condition | None
    allowed_strategy_families: tuple[str, ...]
    forbidden_strategy_families: tuple[str, ...]
    risk_modifiers: Mapping[str, Any]
    rationale: tuple[str, ...]


@dataclass(frozen=True)
class RegimeConfig:
    schema_version: str
    regimes: tuple[RegimeRule, ...]
    required_features: frozenset[str]
    feature_aliases: dict[str, tuple[str, ...]]
    alias_to_canonical: dict[str, str]


@dataclass(frozen=True)
class RegimeDecision:
    regime_id: str
    matched_conditions_summary: str
    allowed_strategy_families: tuple[str, ...]
    forbidden_strategy_families: tuple[str, ...]
    risk_modifiers: Mapping[str, Any]

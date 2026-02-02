"""Selector contract models and canonicalization helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from audit.canonical_json import canonical_json_bytes


class SelectorError(ValueError):
    """Base error for selector contract violations."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SelectorContractError(SelectorError):
    """Raised when selector inputs/outputs fail validation."""


class UnknownStrategyError(SelectorError):
    """Raised when a strategy_id is not registered or unknown."""


class DisallowedStrategyError(SelectorError):
    """Raised when a strategy_id is not allowed by constraints."""


class DeterminismViolationError(SelectorError):
    """Raised when deterministic assumptions are violated."""


@dataclass(frozen=True)
class SelectorInput:
    schema_version: int
    market_state: Mapping[str, Any]
    risk_state: str
    allowed_strategy_ids: Sequence[str]
    constraints: Mapping[str, Any] = field(default_factory=dict)
    timeframe: str | None = None
    snapshot_hash: str | None = None
    universe: Sequence[str] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.schema_version, int) or isinstance(self.schema_version, bool):
            raise SelectorContractError("selector_schema_version_invalid")
        if self.schema_version != 1:
            raise SelectorContractError("selector_schema_version_invalid")
        if not isinstance(self.market_state, Mapping):
            raise SelectorContractError("selector_market_state_invalid")
        for key in self.market_state.keys():
            if not isinstance(key, str):
                raise SelectorContractError("selector_market_state_invalid")
        if not isinstance(self.risk_state, str) or not self.risk_state:
            raise SelectorContractError("selector_risk_state_invalid")
        if not isinstance(self.allowed_strategy_ids, Sequence):
            raise SelectorContractError("selector_allowed_strategies_invalid")
        allowed = []
        for value in self.allowed_strategy_ids:
            if not isinstance(value, str) or not value:
                raise SelectorContractError("selector_allowed_strategies_invalid")
            allowed.append(value)

        if not isinstance(self.constraints, Mapping):
            raise SelectorContractError("selector_constraints_invalid")
        for key in self.constraints.keys():
            if not isinstance(key, str):
                raise SelectorContractError("selector_constraints_invalid")

        if self.timeframe is not None and (
            not isinstance(self.timeframe, str) or not self.timeframe
        ):
            raise SelectorContractError("selector_timeframe_invalid")
        if self.snapshot_hash is not None and (
            not isinstance(self.snapshot_hash, str) or not self.snapshot_hash
        ):
            raise SelectorContractError("selector_snapshot_hash_invalid")

        if self.universe is not None:
            if not isinstance(self.universe, Sequence):
                raise SelectorContractError("selector_universe_invalid")
            universe: list[str] = []
            for value in self.universe:
                if not isinstance(value, str) or not value:
                    raise SelectorContractError("selector_universe_invalid")
                universe.append(value)
            object.__setattr__(self, "universe", tuple(sorted(set(universe))))

        object.__setattr__(self, "allowed_strategy_ids", tuple(sorted(set(allowed))))
        object.__setattr__(self, "market_state", dict(self.market_state))
        object.__setattr__(self, "constraints", dict(self.constraints))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "market_state": dict(self.market_state),
            "risk_state": self.risk_state,
            "allowed_strategy_ids": list(self.allowed_strategy_ids),
            "constraints": dict(self.constraints),
            "timeframe": self.timeframe,
            "snapshot_hash": self.snapshot_hash,
            "universe": list(self.universe) if self.universe is not None else None,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())


@dataclass(frozen=True)
class SelectorOutput:
    schema_version: int
    chosen_strategy_id: str | None
    chosen_strategy_version: int | None
    reason_codes: Sequence[str] = field(default_factory=tuple)
    audit_fields: Mapping[str, Any] = field(default_factory=dict)
    tie_break: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.schema_version, int) or isinstance(self.schema_version, bool):
            raise SelectorContractError("selector_schema_version_invalid")
        if self.schema_version != 1:
            raise SelectorContractError("selector_schema_version_invalid")
        if self.chosen_strategy_id is not None and (
            not isinstance(self.chosen_strategy_id, str) or not self.chosen_strategy_id
        ):
            raise SelectorContractError("selector_strategy_id_invalid")
        if self.chosen_strategy_id is None and self.chosen_strategy_version is not None:
            raise SelectorContractError("selector_strategy_version_invalid")
        if self.chosen_strategy_version is not None and (
            not isinstance(self.chosen_strategy_version, int)
            or isinstance(self.chosen_strategy_version, bool)
        ):
            raise SelectorContractError("selector_strategy_version_invalid")
        if not isinstance(self.reason_codes, Sequence):
            raise SelectorContractError("selector_reason_codes_invalid")
        reason_codes: list[str] = []
        for value in self.reason_codes:
            if not isinstance(value, str):
                raise SelectorContractError("selector_reason_codes_invalid")
            reason_codes.append(value)
        if not isinstance(self.audit_fields, Mapping):
            raise SelectorContractError("selector_audit_fields_invalid")
        for key in self.audit_fields.keys():
            if not isinstance(key, str):
                raise SelectorContractError("selector_audit_fields_invalid")
        if self.tie_break is not None and (
            not isinstance(self.tie_break, str) or not self.tie_break
        ):
            raise SelectorContractError("selector_tie_break_invalid")

        object.__setattr__(self, "reason_codes", tuple(reason_codes))
        object.__setattr__(self, "audit_fields", dict(self.audit_fields))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "chosen_strategy_id": self.chosen_strategy_id,
            "chosen_strategy_version": self.chosen_strategy_version,
            "reason_codes": list(self.reason_codes),
            "audit_fields": dict(self.audit_fields),
            "tie_break": self.tie_break,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())


def canonical_selector_input_bytes(selector_input: SelectorInput) -> bytes:
    return selector_input.canonical_bytes()


def canonical_selector_output_bytes(selector_output: SelectorOutput) -> bytes:
    return selector_output.canonical_bytes()

"""Strategy decision contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Any, Mapping, Sequence

from audit.canonical_json import canonical_json_bytes


DECISION_SCHEMA_VERSION = 1


class DecisionValidationError(ValueError):
    """Raised when strategy decisions fail schema validation."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class DecisionAction(str, Enum):
    HOLD = "HOLD"
    ENTER_LONG = "ENTER_LONG"
    EXIT_LONG = "EXIT_LONG"
    ENTER_SHORT = "ENTER_SHORT"
    EXIT_SHORT = "EXIT_SHORT"


@dataclass(frozen=True)
class DecisionRisk:
    max_position_size: float
    stop_loss: float
    take_profit: float
    policy_ref: str | None = None

    def __post_init__(self) -> None:
        for value in (self.max_position_size, self.stop_loss, self.take_profit):
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                raise DecisionValidationError("decision_risk_invalid")
        if self.policy_ref is not None and (
            not isinstance(self.policy_ref, str) or not self.policy_ref
        ):
            raise DecisionValidationError("decision_risk_invalid")

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "max_position_size": float(self.max_position_size),
            "stop_loss": float(self.stop_loss),
            "take_profit": float(self.take_profit),
        }
        if self.policy_ref is not None:
            payload["policy_ref"] = self.policy_ref
        return payload


@dataclass(frozen=True)
class DecisionProvenance:
    feature_bundle_fingerprint: str
    strategy_id: str
    strategy_params_hash: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.feature_bundle_fingerprint, str)
            or not self.feature_bundle_fingerprint
        ):
            raise DecisionValidationError("decision_provenance_invalid")
        if not isinstance(self.strategy_id, str) or not self.strategy_id:
            raise DecisionValidationError("decision_provenance_invalid")
        if not isinstance(self.strategy_params_hash, str) or not self.strategy_params_hash:
            raise DecisionValidationError("decision_provenance_invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_bundle_fingerprint": self.feature_bundle_fingerprint,
            "strategy_id": self.strategy_id,
            "strategy_params_hash": self.strategy_params_hash,
        }


@dataclass(frozen=True)
class Decision:
    schema_version: int
    as_of_utc: str
    instrument: str
    action: DecisionAction
    rationale: Sequence[str]
    risk: DecisionRisk
    provenance: DecisionProvenance
    confidence: float | None = None

    def __post_init__(self) -> None:
        if self.schema_version != DECISION_SCHEMA_VERSION:
            raise DecisionValidationError("decision_schema_invalid")
        if not isinstance(self.as_of_utc, str) or not self.as_of_utc:
            raise DecisionValidationError("decision_as_of_invalid")
        if not isinstance(self.instrument, str) or not self.instrument:
            raise DecisionValidationError("decision_instrument_invalid")
        if not isinstance(self.action, DecisionAction):
            raise DecisionValidationError("decision_action_invalid")
        if not isinstance(self.rationale, Sequence) or isinstance(self.rationale, str):
            raise DecisionValidationError("decision_rationale_invalid")
        if not self.rationale:
            raise DecisionValidationError("decision_rationale_invalid")
        for item in self.rationale:
            if not isinstance(item, str) or not item:
                raise DecisionValidationError("decision_rationale_invalid")
        if self.confidence is not None:
            if (
                not isinstance(self.confidence, (int, float))
                or isinstance(self.confidence, bool)
                or not (0.0 <= float(self.confidence) <= 1.0)
            ):
                raise DecisionValidationError("decision_confidence_invalid")

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "as_of_utc": self.as_of_utc,
            "instrument": self.instrument,
            "action": self.action.value,
            "rationale": list(self.rationale),
            "risk": self.risk.to_dict(),
            "provenance": self.provenance.to_dict(),
        }
        if self.confidence is not None:
            payload["confidence"] = float(self.confidence)
        return payload


def params_hash(params: Mapping[str, Any]) -> str:
    return sha256(canonical_json_bytes(dict(params))).hexdigest()


def validate_decision_payload(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise DecisionValidationError("decision_payload_invalid")
    if payload.get("schema_version") != DECISION_SCHEMA_VERSION:
        raise DecisionValidationError("decision_schema_invalid")
    if not isinstance(payload.get("as_of_utc"), str) or not payload.get("as_of_utc"):
        raise DecisionValidationError("decision_as_of_invalid")
    if not isinstance(payload.get("instrument"), str) or not payload.get("instrument"):
        raise DecisionValidationError("decision_instrument_invalid")
    action = payload.get("action")
    if action not in {item.value for item in DecisionAction}:
        raise DecisionValidationError("decision_action_invalid")
    rationale = payload.get("rationale")
    if not isinstance(rationale, list) or not rationale:
        raise DecisionValidationError("decision_rationale_invalid")
    risk = payload.get("risk")
    if not isinstance(risk, Mapping):
        raise DecisionValidationError("decision_risk_invalid")
    for key in ("max_position_size", "stop_loss", "take_profit"):
        value = risk.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            raise DecisionValidationError("decision_risk_invalid")
    provenance = payload.get("provenance")
    if not isinstance(provenance, Mapping):
        raise DecisionValidationError("decision_provenance_invalid")
    for key in ("feature_bundle_fingerprint", "strategy_id", "strategy_params_hash"):
        value = provenance.get(key)
        if not isinstance(value, str) or not value:
            raise DecisionValidationError("decision_provenance_invalid")
    confidence = payload.get("confidence")
    if confidence is not None:
        if (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not (0.0 <= float(confidence) <= 1.0)
        ):
            raise DecisionValidationError("decision_confidence_invalid")

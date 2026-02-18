"""Canonical risk contracts and validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from hashlib import sha256
import json
from math import isfinite
from typing import Any


class RiskState(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class Permission(str, Enum):
    ALLOW = "ALLOW"
    RESTRICT = "RESTRICT"
    BLOCK = "BLOCK"


class RiskSeverity(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]


def _normalize_json_value(value: Any) -> JsonValue:
    if isinstance(value, Enum):
        return _normalize_json_value(value.value)
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            if value != value:
                return "NaN"
            return "Infinity" if value > 0 else "-Infinity"
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, JsonValue] = {}
        for key in sorted(value.keys(), key=lambda item: str(item)):
            if not isinstance(key, str):
                raise ValueError("json mapping keys must be strings")
            normalized[key] = _normalize_json_value(value[key])
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize_json_value(item) for item in value]
    raise ValueError(f"non-serializable json value: {type(value).__name__}")


def stable_json_dumps(obj: object) -> str:
    normalized = _normalize_json_value(obj)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_hex(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _normalize_details(details: Mapping[str, Any] | None) -> dict[str, JsonValue]:
    if details is None:
        return {}
    if not isinstance(details, Mapping):
        raise ValueError("risk reason details must be a mapping")
    normalized = _normalize_json_value(details)
    if not isinstance(normalized, dict):
        raise ValueError("risk reason details must normalize to an object")
    return normalized


class RiskReason(str):
    """String-compatible structured reason for deterministic risk decisions."""

    __slots__ = ("rule_id", "severity", "message", "details")

    rule_id: str
    severity: RiskSeverity
    message: str
    details: dict[str, JsonValue]

    def __new__(
        cls,
        rule_id: str,
        *,
        severity: RiskSeverity | str = RiskSeverity.ERROR,
        message: str = "",
        details: Mapping[str, Any] | None = None,
    ) -> "RiskReason":
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise ValueError("risk reason rule_id must be a non-empty string")
        normalized_rule = rule_id.strip()
        if isinstance(severity, str):
            normalized_severity = RiskSeverity(severity.strip().upper())
        elif isinstance(severity, RiskSeverity):
            normalized_severity = severity
        else:
            raise ValueError("risk reason severity must be INFO, WARN, or ERROR")
        if not isinstance(message, str):
            raise ValueError("risk reason message must be a string")
        normalized_message = message.strip() or normalized_rule
        normalized_details = _normalize_details(details)

        obj = str.__new__(cls, normalized_rule)
        object.__setattr__(obj, "rule_id", normalized_rule)
        object.__setattr__(obj, "severity", normalized_severity)
        object.__setattr__(obj, "message", normalized_message)
        object.__setattr__(obj, "details", normalized_details)
        return obj

    @classmethod
    def from_value(cls, value: "RiskReason | str | Mapping[str, Any]") -> "RiskReason":
        if isinstance(value, RiskReason):
            return value
        if isinstance(value, str):
            code = value.strip()
            if not code:
                raise ValueError("risk reason code must be non-empty")
            return cls(code, severity=RiskSeverity.ERROR, message=code, details={})
        if isinstance(value, Mapping):
            return cls(
                str(value.get("rule_id", "")).strip(),
                severity=value.get("severity", RiskSeverity.ERROR),
                message=str(value.get("message", "")).strip(),
                details=value.get("details") if isinstance(value.get("details"), Mapping) else None,
            )
        raise ValueError("risk reason must be a string, mapping, or RiskReason")

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "message": self.message,
            "details": dict(self.details),
        }


def reason_codes(reasons: Sequence[RiskReason | str]) -> list[str]:
    return [RiskReason.from_value(reason).rule_id for reason in reasons]


def reason_payloads(reasons: Sequence[RiskReason | str]) -> list[dict[str, JsonValue]]:
    return [RiskReason.from_value(reason).to_dict() for reason in reasons]


def risk_inputs_digest(inputs: RiskInputs | Mapping[str, Any] | dict[str, Any]) -> str:
    payload: Mapping[str, Any]
    if isinstance(inputs, RiskInputs):
        payload = inputs.to_dict()
    elif isinstance(inputs, Mapping):
        payload = inputs
    else:
        raise ValueError("risk inputs for digest must be RiskInputs or mapping")
    return _sha256_hex(stable_json_dumps(payload))


@dataclass(frozen=True)
class RiskConfig:
    """Shared risk config surface for policy evaluation and gate evaluation."""

    # Gate/state-machine controls.
    missing_red: float = 0.2
    atr_yellow: float | None = None
    atr_red: float | None = None
    rvol_yellow: float | None = None
    rvol_red: float | None = None
    no_metrics_state: RiskState = RiskState.YELLOW

    # Policy/report controls.
    atr_feature: str = "atr_14"
    realized_vol_window: int = 20
    missing_lookback: int = 10
    max_missing_fraction: float = 0.2
    yellow_atr_pct: float = 0.01
    red_atr_pct: float = 0.02
    yellow_vol: float = 0.01
    red_vol: float = 0.02
    recommended_scale_yellow: float = 0.25
    config_version: str = "v1"

    def __post_init__(self) -> None:
        if not 0.0 <= self.missing_red <= 1.0:
            raise ValueError("missing_red must be in [0, 1]")
        if (
            self.atr_yellow is not None
            and self.atr_red is not None
            and self.atr_yellow > self.atr_red
        ):
            raise ValueError("atr_yellow must be <= atr_red")
        if (
            self.rvol_yellow is not None
            and self.rvol_red is not None
            and self.rvol_yellow > self.rvol_red
        ):
            raise ValueError("rvol_yellow must be <= rvol_red")
        if not isinstance(self.no_metrics_state, RiskState):
            raise ValueError("no_metrics_state must be a RiskState")
        if self.realized_vol_window <= 0:
            raise ValueError("realized_vol_window must be > 0")
        if self.missing_lookback <= 0:
            raise ValueError("missing_lookback must be > 0")
        if not (0.0 <= self.max_missing_fraction <= 1.0):
            raise ValueError("max_missing_fraction must be in [0, 1]")
        if not (0.0 < self.yellow_atr_pct < self.red_atr_pct):
            raise ValueError("atr thresholds must satisfy 0 < yellow < red")
        if not (0.0 < self.yellow_vol < self.red_vol):
            raise ValueError("vol thresholds must satisfy 0 < yellow < red")
        if not (0.0 <= self.recommended_scale_yellow <= 1.0):
            raise ValueError("recommended_scale_yellow must be in [0, 1]")
        if not isinstance(self.config_version, str) or not self.config_version.strip():
            raise ValueError("config_version must be a non-empty string")


@dataclass(frozen=True)
class RiskInputs:
    """Typed, validated risk inputs for the permission layer."""

    symbol: str = ""
    timeframe: str = ""
    as_of: str = ""
    atr_pct: float | None = None
    realized_vol: float | None = None
    missing_fraction: float = 0.0
    timestamps_valid: bool = True
    latest_metrics_valid: bool = True
    invalid_index: bool = False
    invalid_close: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RiskInputs":
        return validate_risk_inputs(payload)


@dataclass(frozen=True)
class RiskDecision:
    state: RiskState
    reasons: list[RiskReason] | tuple[RiskReason, ...] = field(default_factory=tuple)
    snapshot: dict[str, Any] = field(default_factory=dict)
    permission: Permission | None = None
    recommended_scale: float | None = None
    config_version: str = "v1"
    inputs_digest: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.state, RiskState):
            raise ValueError("state must be a RiskState")
        if not isinstance(self.reasons, (list, tuple)):
            raise ValueError("reasons must be a list or tuple")
        normalized_reasons = [RiskReason.from_value(reason) for reason in self.reasons]
        if isinstance(self.reasons, tuple):
            object.__setattr__(self, "reasons", tuple(normalized_reasons))
        else:
            object.__setattr__(self, "reasons", normalized_reasons)
        if not isinstance(self.snapshot, dict):
            raise ValueError("snapshot must be a dict")
        if self.permission is not None and not isinstance(self.permission, Permission):
            raise ValueError("permission must be a Permission enum value")
        if self.recommended_scale is not None and not isinstance(
            self.recommended_scale, (int, float)
        ):
            raise ValueError("recommended_scale must be numeric")
        if not isinstance(self.config_version, str) or not self.config_version.strip():
            raise ValueError("config_version must be a non-empty string")
        if self.inputs_digest:
            if not isinstance(self.inputs_digest, str):
                raise ValueError("inputs_digest must be a string")
        else:
            object.__setattr__(self, "inputs_digest", risk_inputs_digest(self.snapshot))


@dataclass(frozen=True)
class RiskContext:
    run_id: str | None = None
    workspace: str | None = None
    symbol: str | None = None
    timeframe: str | None = None


def threshold_snapshot(config: RiskConfig) -> Mapping[str, float]:
    return {
        "yellow_atr_pct": config.yellow_atr_pct,
        "red_atr_pct": config.red_atr_pct,
        "yellow_vol": config.yellow_vol,
        "red_vol": config.red_vol,
        "max_missing_fraction": config.max_missing_fraction,
        "missing_lookback": float(config.missing_lookback),
        "realized_vol_window": float(config.realized_vol_window),
    }


def _require_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _require_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _require_float(value: Any, field: str) -> float:
    if not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    value = float(value)
    if not isfinite(value):
        raise ValueError(f"{field} must be a finite number")
    return value


def _require_optional_float(value: Any, field: str) -> float | None:
    if value is None:
        return None
    return _require_float(value, field)


def _require_iso_datetime(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty ISO timestamp")
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO timestamp") from exc
    return value.strip()


def validate_risk_inputs(payload: Mapping[str, Any] | RiskInputs) -> RiskInputs:
    """Validate and normalize risk inputs. Fail-closed on invalid data."""

    if isinstance(payload, RiskInputs):
        return payload
    if not isinstance(payload, Mapping):
        raise ValueError("risk inputs payload must be a mapping")

    symbol = _require_str(payload.get("symbol"), "symbol")
    timeframe = _require_str(payload.get("timeframe"), "timeframe")
    as_of = _require_iso_datetime(payload.get("as_of"), "as_of")

    atr_pct = _require_optional_float(payload.get("atr_pct"), "atr_pct")
    if atr_pct is not None and atr_pct < 0.0:
        raise ValueError("atr_pct must be >= 0")

    realized_vol = _require_optional_float(payload.get("realized_vol"), "realized_vol")
    if realized_vol is not None and realized_vol < 0.0:
        raise ValueError("realized_vol must be >= 0")

    missing_fraction = _require_float(payload.get("missing_fraction"), "missing_fraction")
    if not 0.0 <= missing_fraction <= 1.0:
        raise ValueError("missing_fraction must be in [0, 1]")

    timestamps_valid = _require_bool(payload.get("timestamps_valid"), "timestamps_valid")
    latest_metrics_valid = _require_bool(
        payload.get("latest_metrics_valid"), "latest_metrics_valid"
    )
    invalid_index = _require_bool(payload.get("invalid_index"), "invalid_index")
    invalid_close = _require_bool(payload.get("invalid_close"), "invalid_close")

    return RiskInputs(
        symbol=symbol,
        timeframe=timeframe,
        as_of=as_of,
        atr_pct=atr_pct,
        realized_vol=realized_vol,
        missing_fraction=missing_fraction,
        timestamps_valid=timestamps_valid,
        latest_metrics_valid=latest_metrics_valid,
        invalid_index=invalid_index,
        invalid_close=invalid_close,
    )

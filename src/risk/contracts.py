"""Canonical risk contracts and validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from math import isfinite
from typing import Any, Mapping


class RiskState(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class Permission(str, Enum):
    ALLOW = "ALLOW"
    RESTRICT = "RESTRICT"
    BLOCK = "BLOCK"


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
    reasons: list[str] | tuple[str, ...] = field(default_factory=tuple)
    snapshot: dict[str, Any] = field(default_factory=dict)
    permission: Permission | None = None
    recommended_scale: float | None = None


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

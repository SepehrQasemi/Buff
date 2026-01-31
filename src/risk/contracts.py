"""Risk input contract and validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from math import isfinite
from typing import Any, Mapping


@dataclass(frozen=True)
class RiskInputs:
    """Typed, validated risk inputs for the permission layer."""

    symbol: str
    timeframe: str
    as_of: str
    atr_pct: float | None
    realized_vol: float | None
    missing_fraction: float
    timestamps_valid: bool
    latest_metrics_valid: bool
    invalid_index: bool
    invalid_close: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RiskInputs":
        return validate_risk_inputs(payload)


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

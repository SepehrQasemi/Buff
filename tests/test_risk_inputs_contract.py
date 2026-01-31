"""Tests for risk input contract validation."""

from __future__ import annotations

from math import nan

import pytest

from risk.contracts import RiskInputs, validate_risk_inputs


pytestmark = pytest.mark.unit


def _valid_payload() -> dict:
    return {
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "as_of": "2024-01-01T00:00:00+00:00",
        "atr_pct": 0.01,
        "realized_vol": 0.02,
        "missing_fraction": 0.0,
        "timestamps_valid": True,
        "latest_metrics_valid": True,
        "invalid_index": False,
        "invalid_close": False,
    }


def test_valid_inputs_pass() -> None:
    payload = _valid_payload()
    result = validate_risk_inputs(payload)
    assert isinstance(result, RiskInputs)
    assert result.symbol == payload["symbol"]


def test_missing_required_field_fails() -> None:
    payload = _valid_payload()
    payload.pop("symbol")
    with pytest.raises(ValueError, match="symbol"):
        validate_risk_inputs(payload)


def test_invalid_types_fail() -> None:
    payload = _valid_payload()
    payload["missing_fraction"] = "0.1"
    with pytest.raises(ValueError, match="missing_fraction"):
        validate_risk_inputs(payload)


def test_negative_and_nan_values_fail() -> None:
    payload = _valid_payload()
    payload["atr_pct"] = -0.01
    with pytest.raises(ValueError, match="atr_pct"):
        validate_risk_inputs(payload)

    payload = _valid_payload()
    payload["realized_vol"] = nan
    with pytest.raises(ValueError, match="realized_vol"):
        validate_risk_inputs(payload)

    payload = _valid_payload()
    payload["missing_fraction"] = 1.5
    with pytest.raises(ValueError, match="missing_fraction"):
        validate_risk_inputs(payload)


def test_serialization_round_trip() -> None:
    payload = _valid_payload()
    inputs = validate_risk_inputs(payload)
    encoded = inputs.to_dict()
    decoded = RiskInputs.from_dict(encoded)
    assert decoded == inputs

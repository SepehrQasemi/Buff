"""Schema validation tests for risk_report.json."""

import json
from pathlib import Path

import pandas as pd
import pytest

from risk.evaluator import evaluate_risk


pytestmark = pytest.mark.unit


def _minimal_validate(schema: dict, payload: dict) -> None:
    required = schema.get("required", [])
    for key in required:
        if key not in payload:
            raise AssertionError(f"Missing required key: {key}")

    metrics_required = schema["properties"]["metrics"]["required"]
    for key in metrics_required:
        if key not in payload["metrics"]:
            raise AssertionError(f"Missing required key in metrics: {key}")

    assert isinstance(payload["reasons"], list)
    assert isinstance(payload["thresholds"], dict)


def _make_payload() -> dict:
    timestamps = pd.date_range("2023-01-01", periods=30, freq="h", tz="UTC")
    ohlcv = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0] * len(timestamps),
            "high": [101.0] * len(timestamps),
            "low": [99.0] * len(timestamps),
            "close": [100.0] * len(timestamps),
        }
    )
    features = pd.DataFrame({"atr_14": [0.5] * len(timestamps)})
    return evaluate_risk(features, ohlcv)


def test_risk_report_schema_validation() -> None:
    schema = json.loads(Path("schemas/risk_report.schema.json").read_text(encoding="utf-8"))
    payload = _make_payload()

    try:
        import jsonschema

        jsonschema.validate(instance=payload, schema=schema)
    except ModuleNotFoundError:
        _minimal_validate(schema, payload)

    assert payload["risk_report_version"] == 1

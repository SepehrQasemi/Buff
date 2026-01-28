"""Contract tests for risk report output."""

import json
from pathlib import Path

import pandas as pd
import pytest

from risk.evaluator import evaluate_risk


pytestmark = pytest.mark.unit


def _make_report() -> dict:
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


def test_risk_report_contract_fields() -> None:
    report = _make_report()
    assert report["risk_report_version"] == 1
    assert isinstance(report["risk_state"], str)
    assert isinstance(report["permission"], str)
    assert isinstance(report["recommended_scale"], float)
    assert isinstance(report["metrics"], dict)
    assert isinstance(report["thresholds"], dict)
    assert isinstance(report["reasons"], list)
    assert report["evaluated_at"] is not None
    parsed = pd.to_datetime(report["evaluated_at"], utc=True, errors="coerce")
    assert not pd.isna(parsed)


def test_risk_report_schema_exists_and_validates() -> None:
    schema_path = Path("schemas/risk_report.schema.json")
    assert schema_path.exists()
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    report = _make_report()

    try:
        import jsonschema

        jsonschema.validate(instance=report, schema=schema)
    except ModuleNotFoundError:
        for key in schema["required"]:
            assert key in report

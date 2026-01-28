"""Tests for knowledge rule specs."""

import json
from pathlib import Path

import pytest

from knowledge.parser import load_and_validate


pytestmark = pytest.mark.unit

REQUIRED_FIELDS = [
    "name",
    "category",
    "inputs",
    "parameters",
    "formula",
    "output",
    "warmup",
    "nan_policy",
    "references",
]


def _load_rules() -> list[dict]:
    path = Path("knowledge/technical_rules.yaml")
    text = path.read_text(encoding="utf-8")
    return json.loads(text)


def test_rules_include_rsi_ema_atr() -> None:
    rules = _load_rules()
    names = {rule.get("name") for rule in rules}
    assert len(rules) == 7
    assert names == {"RSI", "EMA", "ATR", "SMA", "StdDev", "BollingerBands", "MACD"}


def test_rules_have_required_fields() -> None:
    rules = _load_rules()
    for rule in rules:
        for key in REQUIRED_FIELDS:
            assert key in rule, f"Missing {key} in {rule.get('name')}"
        assert isinstance(rule["inputs"], list) and rule["inputs"], "inputs must be non-empty"
        assert isinstance(rule["references"], list) and rule["references"], "references must be non-empty"
        assert isinstance(rule["formula"], str) and rule["formula"].strip(), "formula required"


def test_rules_resample_policy() -> None:
    rules = _load_rules()
    for rule in rules:
        policy = rule.get("resample_policy", {})
        assert "rule" in policy, f"resample_policy.rule missing for {rule.get('name')}"
        assert "compute after resampling" in policy["rule"].lower(), (
            f"resample_policy must enforce compute after resampling for {rule.get('name')}"
        )


def test_schema_validator_rejects_empty(tmp_path: Path) -> None:
    empty_path = tmp_path / "empty_rules.json"
    empty_path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_and_validate(empty_path, Path("knowledge/schema.yaml"))

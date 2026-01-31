"""Contract tests for knowledge rule specs."""

import json
from pathlib import Path

import pytest

from knowledge.parser import load_and_validate


pytestmark = pytest.mark.unit

REQUIRED_FIELDS = [
    "id",
    "name",
    "category",
    "description",
    "inputs",
    "parameters",
    "formula",
    "output",
    "warmup",
    "nan_policy",
    "resample_policy",
    "lookahead_policy",
    "references",
]

ALLOWED_INPUTS = {"open", "high", "low", "close", "volume"}
FORBIDDEN_WORDS = [
    "buy",
    "sell",
    "long",
    "short",
    "bullish",
    "bearish",
    "predict",
    "prediction",
    "forecast",
]


def _load_rules() -> list[dict]:
    path = Path("knowledge/technical_rules.yaml")
    text = path.read_text(encoding="utf-8")
    return json.loads(text)


def _has_forbidden_words(text: str) -> list[str]:
    lower = text.lower()
    return [word for word in FORBIDDEN_WORDS if word in lower]


def test_rules_load_and_validate_schema() -> None:
    rules = load_and_validate(Path("knowledge/technical_rules.yaml"), Path("knowledge/schema.yaml"))
    assert isinstance(rules, list)
    assert rules, "rules must not be empty"
    for rule in rules:
        assert isinstance(rule, dict), "each rule must be a dict"


def test_rules_have_required_fields() -> None:
    rules = _load_rules()
    ids = []
    for rule in rules:
        for key in REQUIRED_FIELDS:
            assert key in rule, f"Missing {key} in {rule.get('name')}"
        ids.append(rule.get("id"))
        assert isinstance(rule["inputs"], list) and rule["inputs"], "inputs must be non-empty"
        assert all(isinstance(item, str) for item in rule["inputs"]), "inputs must be strings"
        assert set(rule["inputs"]).issubset(ALLOWED_INPUTS), "inputs contain invalid fields"
        assert isinstance(rule["parameters"], dict), "parameters must be a dict"
        assert isinstance(rule["references"], list) and rule["references"], (
            "references must be non-empty"
        )
        assert isinstance(rule["formula"], str) and rule["formula"].strip(), "formula required"
        description = rule.get("description", "")
        assert isinstance(description, str) and description.strip(), "description required"
        forbidden = _has_forbidden_words(description)
        assert not forbidden, f"forbidden words in description: {forbidden}"
    assert len(ids) == len(set(ids)), "rule ids must be unique"


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

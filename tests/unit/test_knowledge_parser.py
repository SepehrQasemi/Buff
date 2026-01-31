"""Unit tests for knowledge parser skeleton."""

from pathlib import Path

import pytest

from knowledge.parser import load_and_validate


pytestmark = pytest.mark.unit


def test_valid_rule(tmp_path: Path) -> None:
    payload = """[
      {
        "id": "rsi_cross",
        "name": "RSI Cross",
        "inputs": ["close"],
        "formula": "RSI(close, 14)",
        "parameters": {"period": 14},
        "references": ["https://example.com/rsi"]
      }
    ]"""
    path = tmp_path / "rules.yaml"
    path.write_text(payload.strip(), encoding="utf-8")

    schema_path = tmp_path / "schema.yaml"
    schema_path.write_text(
        '{"required_keys": ["id", "name", "inputs", "formula", "parameters", "references"]}',
        encoding="utf-8",
    )

    rules = load_and_validate(path, schema_path)
    assert len(rules) == 1


def test_invalid_rule_missing_key(tmp_path: Path) -> None:
    payload = """[
      {
        "id": "missing_formula",
        "name": "Missing Formula",
        "inputs": ["close"],
        "parameters": {},
        "references": []
      }
    ]"""
    path = tmp_path / "rules.yaml"
    path.write_text(payload.strip(), encoding="utf-8")

    with pytest.raises(ValueError):
        load_and_validate(path, schema_path=None)

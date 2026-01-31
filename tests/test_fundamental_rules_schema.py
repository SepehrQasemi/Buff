"""Schema validation tests for fundamental risk rules."""

from __future__ import annotations

from pathlib import Path

from risk_fundamental.schemas import load_rules


def test_fundamental_rules_schema_valid() -> None:
    rules = load_rules(Path("knowledge") / "fundamental_risk_rules.yaml")
    assert rules["meta"]["purpose"] == "fundamental_risk_permission_only"
    assert "rules" in rules

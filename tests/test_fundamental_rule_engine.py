"""Rule engine evaluation tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from risk_fundamental.contracts import FundamentalSnapshot
from risk_fundamental.engine import FundamentalRiskEngine


def _engine() -> FundamentalRiskEngine:
    engine = FundamentalRiskEngine()
    engine.load_rules(Path("knowledge") / "fundamental_risk_rules.yaml")
    return engine


def test_rule_engine_matches_macro_rule() -> None:
    engine = _engine()
    snapshot = FundamentalSnapshot(
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        macro={"fed_rate_change": 1.0},
        onchain={},
        news={},
        provenance={"source": "unit"},
    )
    decision = engine.compute(snapshot)
    matched_ids = {item.rule_id for item in decision.evidence if item.matched}
    assert "MACRO_001" in matched_ids


def test_rule_engine_deterministic() -> None:
    engine = _engine()
    snapshot = FundamentalSnapshot(
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        macro={"fed_rate_change": 1.0},
        onchain={},
        news={},
        provenance={"source": "unit"},
    )
    decision_a = engine.compute(snapshot)
    decision_b = engine.compute(snapshot)
    assert decision_a == decision_b

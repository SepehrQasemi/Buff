"""Artifact writer tests for fundamental risk decisions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from risk_fundamental.artifacts import write_latest, write_timeline
from risk_fundamental.contracts import Evidence
from risk_fundamental.engine import FundamentalRiskDecision


def _decision() -> FundamentalRiskDecision:
    return FundamentalRiskDecision(
        timestamp=datetime(2026, 1, 5, tzinfo=timezone.utc),
        macro_risk_state="low",
        onchain_stress_level="normal",
        news_risk_flag=False,
        final_risk_state="green",
        trade_permission=True,
        size_multiplier=1.0,
        missing_inputs=[],
        evidence=[
            Evidence(
                rule_id="MACRO_001",
                domain="macro",
                matched=False,
                severity=0.9,
                inputs_used={"fed_rate_change": 0.0},
                reason="gte:fed_rate_change:0.0",
            )
        ],
    )


def test_artifacts_written(tmp_path: Path) -> None:
    latest_path = tmp_path / "fundamental_risk_latest.json"
    timeline_path = tmp_path / "fundamental_risk_timeline.json"
    decision = _decision()

    write_latest(decision, latest_path)
    write_timeline(decision, timeline_path)

    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    assert latest["final_risk_state"] == "green"
    assert latest["size_multiplier"] == 1.0

    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    assert isinstance(timeline, list)
    assert timeline[0]["final_risk_state"] == "green"

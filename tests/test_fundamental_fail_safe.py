"""Fail-safe behavior tests for fundamental risk."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from risk_fundamental.contracts import FundamentalSnapshot
from risk_fundamental.engine import FundamentalRiskEngine


def test_missing_critical_forces_yellow() -> None:
    engine = FundamentalRiskEngine()
    engine.load_rules(Path("knowledge") / "fundamental_risk_rules.yaml")
    snapshot = FundamentalSnapshot(
        timestamp=datetime(2026, 1, 4, tzinfo=timezone.utc),
        macro={
            "fed_rate_change": 0.0,
            "cpi_actual": 3.0,
            "cpi_expected": 3.1,
        },
        onchain={
            "nvt_ratio": 1.0,
            "mvrv_ratio": 2.0,
            "exchange_netflow_zscore": 0.0,
        },
        news={
            "event_importance": "low",
            "minutes_to_event": 999,
            "gdelt_event_count_zscore": 0.0,
        },
        provenance={"source": "unit"},
    )
    decision = engine.compute(snapshot)
    assert "token_unlock_pct_7d" in decision.missing_inputs
    assert decision.final_risk_state == "yellow"

"""Aggregation behavior tests for fundamental risk."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from risk_fundamental.contracts import FundamentalSnapshot
from risk_fundamental.engine import FundamentalRiskEngine


def _engine() -> FundamentalRiskEngine:
    engine = FundamentalRiskEngine()
    engine.load_rules(Path("knowledge") / "fundamental_risk_rules.yaml")
    return engine


def test_aggregation_red_priority() -> None:
    engine = _engine()
    snapshot = FundamentalSnapshot(
        timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc),
        macro={"fed_rate_change": 1.0},
        onchain={},
        news={},
        provenance={"source": "unit"},
    )
    decision = engine.compute(snapshot)
    assert decision.final_risk_state == "red"
    assert decision.trade_permission is False
    assert decision.size_multiplier == 0.0


def test_aggregation_green_when_defaults_and_no_missing() -> None:
    engine = _engine()
    snapshot = FundamentalSnapshot(
        timestamp=datetime(2026, 1, 3, tzinfo=timezone.utc),
        macro={
            "fed_rate_change": 0.0,
            "cpi_actual": 3.0,
            "cpi_expected": 3.1,
        },
        onchain={
            "nvt_ratio": 1.0,
            "mvrv_ratio": 2.0,
            "exchange_netflow_zscore": 0.0,
            "token_unlock_pct_7d": 1.0,
        },
        news={
            "event_importance": "low",
            "minutes_to_event": 999,
            "gdelt_event_count_zscore": 0.0,
        },
        provenance={"source": "unit"},
    )
    decision = engine.compute(snapshot)
    assert decision.final_risk_state == "green"
    assert decision.trade_permission is True
    assert decision.size_multiplier == 1.0

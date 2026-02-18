from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from risk.state_machine import RiskConfig, RiskState
from risk.veto import risk_veto


INVALID_INPUT_CASES: tuple[dict[str, object], ...] = (
    {},
    {"symbol": "BTCUSDT"},
    {
        "symbol": "BTCUSDT",
        "timeframe": "1m",
        "as_of": "not-a-timestamp",
        "atr_pct": -1.0,
        "realized_vol": 0.01,
        "missing_fraction": 0.0,
        "timestamps_valid": True,
        "latest_metrics_valid": True,
        "invalid_index": False,
        "invalid_close": False,
    },
)


def _config() -> RiskConfig:
    return RiskConfig(
        missing_red=0.2,
        atr_yellow=0.02,
        atr_red=0.05,
        rvol_yellow=0.02,
        rvol_red=0.05,
    )


@pytest.mark.parametrize("invalid_inputs", INVALID_INPUT_CASES)
def test_s4_fail_closed_on_invalid_inputs(invalid_inputs: dict[str, object]) -> None:
    decision, audit_event = risk_veto(invalid_inputs, _config())

    assert decision.state is RiskState.RED
    assert decision.reasons
    assert all(isinstance(reason, str) and reason for reason in decision.reasons)
    assert isinstance(decision.snapshot, dict) and decision.snapshot

    assert audit_event.component == "risk_veto"
    assert audit_event.action == "evaluate"
    assert audit_event.decision == RiskState.RED.value
    assert audit_event.reasons
    assert all(isinstance(reason, str) and reason for reason in audit_event.reasons)
    assert isinstance(audit_event.snapshot, dict) and audit_event.snapshot

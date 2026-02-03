from __future__ import annotations

import pytest

from strategy_registry.decision import (
    Decision,
    DecisionAction,
    DecisionProvenance,
    DecisionRisk,
    DecisionValidationError,
    validate_decision_payload,
)


def test_decision_schema_version_rejected() -> None:
    with pytest.raises(DecisionValidationError):
        Decision(
            schema_version=0,
            as_of_utc="2025-01-01T00:00:00Z",
            instrument="BTCUSDT",
            action=DecisionAction.HOLD,
            rationale=["no_signal"],
            risk=DecisionRisk(max_position_size=1.0, stop_loss=0.01, take_profit=0.02),
            provenance=DecisionProvenance(
                feature_bundle_fingerprint="abc",
                strategy_id="demo@1.0.0",
                strategy_params_hash="hash",
            ),
        )


def test_decision_payload_missing_fields() -> None:
    payload = {
        "schema_version": 1,
        "as_of_utc": "2025-01-01T00:00:00Z",
        "instrument": "BTCUSDT",
        "action": "HOLD",
    }
    with pytest.raises(DecisionValidationError):
        validate_decision_payload(payload)

from __future__ import annotations

import pytest

from audit.decision_record import (
    Artifacts,
    CodeVersion,
    DecisionRecord,
    Inputs,
    Outcome,
    RunContext,
    Selection,
)
from audit.replay import ReplayMissingConfigError, ReplayRunner
from audit.snapshot import Snapshot


def test_replay_fails_closed_on_missing_risk_config() -> None:
    record = DecisionRecord(
        decision_id="dec-missing",
        ts_utc="2026-02-01T00:00:00Z",
        symbol="BTCUSDT",
        timeframe="1m",
        code_version=CodeVersion(git_commit="deadbeef", dirty=False),
        run_context=RunContext(seed=42, python="3.11.9", platform="linux"),
        artifacts=Artifacts(snapshot_ref=None, features_ref=None),
        inputs=Inputs(
            market_features={"trend_state": "up"},
            risk_state="GREEN",
            selector_inputs={},
            config={},
            risk_mode="computed",
        ),
        selection=Selection(
            selected=False,
            strategy_id=None,
            status="no_selection",
            score=None,
            reasons=[],
            rules_fired=[],
        ),
        outcome=Outcome(decision="SKIP", allowed=True, notes=None),
    )
    snapshot = Snapshot(
        snapshot_version=1,
        decision_id="dec-missing",
        symbol="BTCUSDT",
        timeframe="1m",
        market_data=None,
        features={"trend_state": "up"},
        risk_inputs={
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "as_of": "2026-02-01T00:00:00Z",
            "atr_pct": 0.005,
            "realized_vol": 0.004,
            "missing_fraction": 0.0,
            "timestamps_valid": True,
            "latest_metrics_valid": True,
            "invalid_index": False,
            "invalid_close": False,
        },
        config=None,
        selector_inputs={},
    )

    with pytest.raises(ReplayMissingConfigError):
        ReplayRunner().replay(record, snapshot, strict_core=True)


def test_missing_config_error_message_contains_field_path() -> None:
    record = DecisionRecord(
        decision_id="dec-missing",
        ts_utc="2026-02-01T00:00:00Z",
        symbol="BTCUSDT",
        timeframe="1m",
        code_version=CodeVersion(git_commit="deadbeef", dirty=False),
        run_context=RunContext(seed=42, python="3.11.9", platform="linux"),
        artifacts=Artifacts(snapshot_ref=None, features_ref=None),
        inputs=Inputs(
            market_features={"trend_state": "up"},
            risk_state="GREEN",
            selector_inputs={},
            config={},
            risk_mode="computed",
        ),
        selection=Selection(
            selected=False,
            strategy_id=None,
            status="no_selection",
            score=None,
            reasons=[],
            rules_fired=[],
        ),
        outcome=Outcome(decision="SKIP", allowed=True, notes=None),
    )
    snapshot = Snapshot(
        snapshot_version=1,
        decision_id="dec-missing",
        symbol="BTCUSDT",
        timeframe="1m",
        market_data=None,
        features={"trend_state": "up"},
        risk_inputs={
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "as_of": "2026-02-01T00:00:00Z",
            "atr_pct": 0.005,
            "realized_vol": 0.004,
            "missing_fraction": 0.0,
            "timestamps_valid": True,
            "latest_metrics_valid": True,
            "invalid_index": False,
            "invalid_close": False,
        },
        config=None,
        selector_inputs={},
    )

    with pytest.raises(ReplayMissingConfigError) as exc:
        ReplayRunner().replay(record, snapshot, strict_core=True)
    assert "inputs.config.risk_config" in str(exc.value)

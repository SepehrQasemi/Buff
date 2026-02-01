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
from audit.replay import ReplayConfigMismatchError, ReplayMissingConfigError, ReplayRunner
from audit.snapshot import Snapshot
from risk.types import RiskState
from selector.records import selection_to_record
from selector.selector import select_strategy


def _base_record(config: dict | None) -> DecisionRecord:
    market_features = {"trend_state": "up"}
    selection_result = select_strategy(market_features, RiskState.GREEN)
    selection_record = selection_to_record(selection_result)
    return DecisionRecord(
        decision_id="dec-config",
        ts_utc="2026-02-01T00:00:00Z",
        symbol="BTCUSDT",
        timeframe="1m",
        code_version=CodeVersion(git_commit="deadbeef", dirty=False),
        run_context=RunContext(seed=1, python="3.11.9", platform="linux"),
        artifacts=Artifacts(snapshot_ref=None, features_ref=None),
        inputs=Inputs(
            market_features=market_features,
            risk_state="GREEN",
            selector_inputs={},
            config={"risk_config": config} if config is not None else {},
            risk_mode="computed",
        ),
        selection=Selection(
            selected=False,
            strategy_id=None,
            status="no_selection",
            score=None,
            reasons=[selection_record["reason"]],
            rules_fired=[selection_record["rule_id"]],
        ),
        outcome=Outcome(decision="SKIP", allowed=True, notes=None),
    )


def _base_snapshot(config: dict | None) -> Snapshot:
    return Snapshot(
        snapshot_version=1,
        decision_id="dec-config",
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
        config={"risk_config": config} if config is not None else None,
        selector_inputs={},
    )


def test_config_record_only_is_used() -> None:
    record = _base_record({"missing_red": 0.2})
    snapshot = _base_snapshot(None)
    report = ReplayRunner().replay(record, snapshot, strict_core=True)
    assert report.matched


def test_config_snapshot_only_is_used() -> None:
    record = _base_record(None)
    snapshot = _base_snapshot({"missing_red": 0.2})
    report = ReplayRunner().replay(record, snapshot, strict_core=True)
    assert report.matched


def test_config_both_equal_ok() -> None:
    cfg = {"missing_red": 0.2}
    record = _base_record(cfg)
    snapshot = _base_snapshot(cfg)
    report = ReplayRunner().replay(record, snapshot, strict_core=True)
    assert report.matched


def test_config_both_mismatch_fails() -> None:
    record = _base_record({"missing_red": 0.2})
    snapshot = _base_snapshot({"missing_red": 0.3})
    with pytest.raises(ReplayConfigMismatchError):
        ReplayRunner().replay(record, snapshot, strict_core=True)


def test_config_missing_fails_when_risk_inputs_present() -> None:
    record = _base_record(None)
    snapshot = _base_snapshot(None)
    with pytest.raises(ReplayMissingConfigError):
        ReplayRunner().replay(record, snapshot, strict_core=True)


def test_config_optional_when_no_snapshot_risk_inputs() -> None:
    record = _base_record(None)
    record = DecisionRecord(
        decision_id=record.decision_id,
        ts_utc=record.ts_utc,
        symbol=record.symbol,
        timeframe=record.timeframe,
        code_version=record.code_version,
        run_context=record.run_context,
        artifacts=record.artifacts,
        inputs=Inputs(
            market_features=record.inputs.market_features,
            risk_state=record.inputs.risk_state,
            selector_inputs=record.inputs.selector_inputs,
            config=record.inputs.config,
            risk_mode="fact",
        ),
        selection=record.selection,
        outcome=record.outcome,
    )
    snapshot = Snapshot(
        snapshot_version=1,
        decision_id="dec-config",
        symbol="BTCUSDT",
        timeframe="1m",
        market_data=None,
        features={"trend_state": "up"},
        risk_inputs=None,
        config=None,
        selector_inputs={},
    )
    report = ReplayRunner().replay(record, snapshot, strict_core=True)
    assert report.matched

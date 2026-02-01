from __future__ import annotations

from audit.decision_record import (
    Artifacts,
    CodeVersion,
    DecisionRecord,
    Inputs,
    Outcome,
    RunContext,
    Selection,
)
from audit.replay import ReplayConfig, ReplayRunner
import pytest

from audit.snapshot import Snapshot
from risk.types import RiskState
from selector.records import selection_to_record
from selector.selector import select_strategy


def _record_and_snapshot() -> tuple[DecisionRecord, Snapshot]:
    market_features = {
        "trend_state": "up",
        "volatility_regime": "low",
        "structure_state": "breakout",
    }
    selection_result = select_strategy(market_features, RiskState.GREEN)
    selection_record = selection_to_record(selection_result)
    selection = Selection(
        selected=True,
        strategy_id=selection_record["strategy_id"],
        status="selected",
        score=None,
        reasons=[selection_record["reason"]],
        rules_fired=[selection_record["rule_id"]],
    )
    record = DecisionRecord(
        decision_id="dec-strict",
        ts_utc="2026-02-01T00:00:00Z",
        symbol="BTCUSDT",
        timeframe="1m",
        code_version=CodeVersion(git_commit="deadbeef", dirty=False),
        run_context=RunContext(seed=42, python="3.11.9", platform="linux"),
        artifacts=Artifacts(snapshot_ref=None, features_ref=None),
        inputs=Inputs(
            market_features=market_features,
            risk_state="GREEN",
            selector_inputs={},
            config={"risk_config": {"missing_red": 0.2}},
            risk_mode="fact",
        ),
        selection=selection,
        outcome=Outcome(decision="SELECT", allowed=True, notes=None),
    )
    snapshot = Snapshot(
        snapshot_version=1,
        decision_id="dec-strict",
        symbol="BTCUSDT",
        timeframe="1m",
        market_data=None,
        features=market_features,
        risk_inputs=None,
        config=None,
        selector_inputs={},
    )
    return record, snapshot


def test_strict_core_passes_with_new_ts_and_platform() -> None:
    record, snapshot = _record_and_snapshot()
    runner = ReplayRunner(
        config=ReplayConfig(
            ts_utc_override="2026-02-01T01:00:00Z",
            run_context_override=RunContext(seed=42, python="3.11.10", platform="darwin"),
        )
    )
    report = runner.replay(record, snapshot, strict_core=True)
    assert report.matched


def test_strict_full_fails_if_ts_changes_unless_preserved() -> None:
    record, snapshot = _record_and_snapshot()
    runner = ReplayRunner(config=ReplayConfig(ts_utc_override="2026-02-01T01:00:00Z"))
    report = runner.replay(record, snapshot, strict_full=True)
    assert report.matched


def test_strict_full_fails_on_run_context_changes() -> None:
    record, snapshot = _record_and_snapshot()
    runner = ReplayRunner(
        config=ReplayConfig(
            run_context_override=RunContext(seed=42, python="3.11.10", platform="darwin")
        )
    )
    report = runner.replay(record, snapshot, strict_full=True)
    assert report.matched


def test_strict_full_ignores_metadata_overrides() -> None:
    record, snapshot = _record_and_snapshot()
    runner = ReplayRunner(
        config=ReplayConfig(
            ts_utc_override="2026-02-01T01:00:00Z",
            run_context_override=RunContext(seed=42, python="3.11.10", platform="darwin"),
        )
    )
    report = runner.replay(record, snapshot, strict_full=True)
    assert report.matched


def test_non_strict_ignores_metadata_changes() -> None:
    record, snapshot = _record_and_snapshot()
    runner = ReplayRunner(
        config=ReplayConfig(
            ts_utc_override="2026-02-01T01:00:00Z",
            run_context_override=RunContext(seed=42, python="3.11.10", platform="darwin"),
        )
    )
    report = runner.replay(record, snapshot)
    assert report.matched


def test_record_only_replay_risk_semantics_fact_mode() -> None:
    record, snapshot = _record_and_snapshot()
    snapshot = Snapshot(
        snapshot_version=1,
        decision_id=record.decision_id,
        symbol=record.symbol,
        timeframe=record.timeframe,
        market_data=None,
        features=record.inputs.market_features,
        risk_inputs=None,
        config=None,
        selector_inputs={},
    )
    report = ReplayRunner().replay(record, snapshot, strict_core=True)
    assert report.matched


def test_record_only_replay_requires_config_when_computed_mode() -> None:
    record, snapshot = _record_and_snapshot()
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
            risk_mode="computed",
        ),
        selection=record.selection,
        outcome=record.outcome,
    )
    snapshot = Snapshot(
        snapshot_version=1,
        decision_id=record.decision_id,
        symbol=record.symbol,
        timeframe=record.timeframe,
        market_data=None,
        features=record.inputs.market_features,
        risk_inputs=None,
        config=None,
        selector_inputs={},
    )
    from audit.replay import ReplayMissingConfigError

    with pytest.raises(ReplayMissingConfigError):
        ReplayRunner().replay(record, snapshot, strict_core=True)

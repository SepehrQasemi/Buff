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
from audit.replay import ReplayRunner
from audit.snapshot import Snapshot
from risk.contracts import RiskState
from selector.records import selection_to_record
from selector.selector import select_strategy


def test_replay_mismatch_emits_diff_paths() -> None:
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
        decision_id="dec-002",
        ts_utc="2026-02-01T00:00:00Z",
        symbol="BTCUSDT",
        timeframe="1m",
        code_version=CodeVersion(git_commit="deadbeef", dirty=False),
        run_context=RunContext(seed=7, python="3.11.9", platform="linux"),
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
        decision_id="dec-002",
        symbol="BTCUSDT",
        timeframe="1m",
        market_data=None,
        features={
            "trend_state": "flat",
            "volatility_regime": "mid",
            "structure_state": "meanrevert",
        },
        risk_inputs=None,
        config=None,
        selector_inputs={},
    )

    report = ReplayRunner().replay(record, snapshot)
    assert not report.matched
    assert any(diff.path == "selection.strategy_id" for diff in report.diffs)

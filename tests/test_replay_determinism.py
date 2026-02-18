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
from risk.contracts import validate_risk_inputs
from risk.contracts import RiskConfig
from risk.state_machine import evaluate_risk
from risk.contracts import RiskState
from selector.records import selection_to_record
from selector.selector import select_strategy


def test_replay_matches_with_fixed_seed() -> None:
    market_features = {
        "trend_state": "up",
        "volatility_regime": "low",
        "structure_state": "breakout",
    }
    risk_inputs = {
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
    }
    cfg = RiskConfig(
        missing_red=0.2,
        atr_yellow=0.01,
        atr_red=0.02,
        rvol_yellow=0.01,
        rvol_red=0.02,
    )
    validated = validate_risk_inputs(risk_inputs)
    risk_decision = evaluate_risk(validated, cfg)
    risk_state = risk_decision.state.value
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
        decision_id="dec-001",
        ts_utc="2026-02-01T00:00:00Z",
        symbol="BTCUSDT",
        timeframe="1m",
        code_version=CodeVersion(git_commit="deadbeef", dirty=False),
        run_context=RunContext(seed=42, python="3.11.9", platform="linux"),
        artifacts=Artifacts(snapshot_ref=None, features_ref=None),
        inputs=Inputs(
            market_features=market_features,
            risk_state=risk_state,
            selector_inputs={"selector_version": 1},
            config={
                "risk_config": {
                    "missing_red": 0.2,
                    "atr_yellow": 0.01,
                    "atr_red": 0.02,
                    "rvol_yellow": 0.01,
                    "rvol_red": 0.02,
                    "no_metrics_state": "YELLOW",
                }
            },
            risk_mode="computed",
        ),
        selection=selection,
        outcome=Outcome(decision="SELECT", allowed=True, notes=None),
    )

    snapshot = Snapshot(
        snapshot_version=1,
        decision_id="dec-001",
        symbol="BTCUSDT",
        timeframe="1m",
        market_data=None,
        features=market_features,
        risk_inputs=risk_inputs,
        config={
            "risk_config": {
                "missing_red": 0.2,
                "atr_yellow": 0.01,
                "atr_red": 0.02,
                "rvol_yellow": 0.01,
                "rvol_red": 0.02,
                "no_metrics_state": "YELLOW",
            }
        },
        selector_inputs={"selector_version": 1},
    )

    runner = ReplayRunner()
    report = runner.replay(record, snapshot, strict_core=True)
    assert report.matched
    assert record.hashes is not None
    assert report.replay_record.hashes is not None
    assert record.hashes.content_hash == report.replay_record.hashes.content_hash

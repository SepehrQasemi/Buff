from __future__ import annotations

import json

from audit.decision_record import (
    Artifacts,
    CodeVersion,
    DecisionRecord,
    Inputs,
    Outcome,
    RunContext,
    Selection,
)


def _make_record() -> DecisionRecord:
    return DecisionRecord(
        decision_id="dec-001",
        ts_utc="2026-02-01T00:00:00Z",
        symbol="BTCUSDT",
        timeframe="1m",
        code_version=CodeVersion(git_commit="deadbeef", dirty=False),
        run_context=RunContext(seed=123, python="3.11.9", platform="linux"),
        artifacts=Artifacts(snapshot_ref=None, features_ref=None),
        inputs=Inputs(
            market_features={"atr_pct": 0.123456789, "trend_state": "up"},
            risk_state="GREEN",
            selector_inputs={"volatility_regime": "low"},
            config={"risk_config": {"missing_red": 0.2}},
            risk_mode="fact",
        ),
        selection=Selection(
            selected=True,
            strategy_id="TREND_FOLLOW",
            status="selected",
            score=1.234567891,
            reasons=["trend+breakout & vol not high"],
            rules_fired=["R2"],
        ),
        outcome=Outcome(decision="SELECT", allowed=True, notes=None),
    )


def test_canonical_json_stable_and_hashes() -> None:
    record = _make_record()
    first = record.to_canonical_json()
    second = record.to_canonical_json()
    assert first == second

    payload = json.loads(first)
    loaded = DecisionRecord.from_dict(payload)
    assert record.hashes is not None
    assert loaded.hashes is not None
    assert record.hashes.inputs_hash == loaded.hashes.inputs_hash
    assert record.hashes.core_hash == loaded.hashes.core_hash
    assert record.hashes.content_hash == loaded.hashes.content_hash


def test_float_formatting_is_fixed_precision() -> None:
    record = _make_record()
    text = record.to_canonical_json()
    assert '"atr_pct":0.12345679' in text
    assert '"score":1.23456789' in text

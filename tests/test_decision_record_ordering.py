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


def _base_record(selection: Selection) -> DecisionRecord:
    return DecisionRecord(
        decision_id="dec-order",
        ts_utc="2026-02-01T00:00:00Z",
        symbol="BTCUSDT",
        timeframe="1m",
        code_version=CodeVersion(git_commit="deadbeef", dirty=False),
        run_context=RunContext(seed=1, python="3.11.9", platform="linux"),
        artifacts=Artifacts(snapshot_ref=None, features_ref=None),
        inputs=Inputs(
            market_features={"trend_state": "up"},
            risk_state="GREEN",
            selector_inputs={},
            config={"risk_config": {"missing_red": 0.2}},
            risk_mode="fact",
        ),
        selection=selection,
        outcome=Outcome(decision="SELECT", allowed=True, notes=None),
    )


def test_rules_fired_sorted_before_hashing() -> None:
    sel_a = Selection(
        selected=True,
        strategy_id="TREND_FOLLOW",
        status="selected",
        score=None,
        reasons=["b", "a"],
        rules_fired=["R2", "R1"],
    )
    sel_b = Selection(
        selected=True,
        strategy_id="TREND_FOLLOW",
        status="selected",
        score=None,
        reasons=["a", "b"],
        rules_fired=["R1", "R2"],
    )
    rec_a = _base_record(sel_a)
    rec_b = _base_record(sel_b)
    assert rec_a.hashes is not None
    assert rec_b.hashes is not None
    assert rec_a.hashes.core_hash == rec_b.hashes.core_hash


def test_rules_fired_content_changes_hash() -> None:
    sel_a = Selection(
        selected=True,
        strategy_id="TREND_FOLLOW",
        status="selected",
        score=None,
        reasons=["a"],
        rules_fired=["R1"],
    )
    sel_b = Selection(
        selected=True,
        strategy_id="TREND_FOLLOW",
        status="selected",
        score=None,
        reasons=["a"],
        rules_fired=["R2"],
    )
    rec_a = _base_record(sel_a)
    rec_b = _base_record(sel_b)
    assert rec_a.hashes is not None
    assert rec_b.hashes is not None
    assert rec_a.hashes.core_hash != rec_b.hashes.core_hash


def test_reasons_sorted_before_hashing() -> None:
    sel_a = Selection(
        selected=True,
        strategy_id="TREND_FOLLOW",
        status="selected",
        score=None,
        reasons=["z", "a", "m"],
        rules_fired=["R2"],
    )
    sel_b = Selection(
        selected=True,
        strategy_id="TREND_FOLLOW",
        status="selected",
        score=None,
        reasons=["a", "m", "z"],
        rules_fired=["R2"],
    )
    rec_a = _base_record(sel_a)
    rec_b = _base_record(sel_b)
    assert rec_a.hashes is not None
    assert rec_b.hashes is not None
    assert rec_a.hashes.core_hash == rec_b.hashes.core_hash


def test_no_selection_serializes_strategy_id_null() -> None:
    selection = Selection(
        selected=False,
        strategy_id=None,
        status="no_selection",
        score=None,
        reasons=[],
        rules_fired=[],
    )
    record = _base_record(selection)
    text = record.to_canonical_json()
    assert '"strategy_id":null' in text


def test_no_selection_core_hash_stable() -> None:
    selection = Selection(
        selected=False,
        strategy_id=None,
        status="no_selection",
        score=None,
        reasons=[],
        rules_fired=[],
    )
    record = _base_record(selection)
    record_alt = DecisionRecord(
        decision_id="dec-order",
        ts_utc="2026-02-01T01:00:00Z",
        symbol="BTCUSDT",
        timeframe="1m",
        code_version=CodeVersion(git_commit="deadbeef", dirty=False),
        run_context=RunContext(seed=2, python="3.11.10", platform="darwin"),
        artifacts=Artifacts(snapshot_ref=None, features_ref=None),
        inputs=record.inputs,
        selection=record.selection,
        outcome=record.outcome,
    )
    assert record.hashes is not None
    assert record_alt.hashes is not None
    assert record.hashes.core_hash == record_alt.hashes.core_hash

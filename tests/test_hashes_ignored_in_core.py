from __future__ import annotations

from audit.decision_record import (
    Artifacts,
    CodeVersion,
    DecisionRecord,
    Inputs,
    Outcome,
    RunContext,
    Selection,
    canonicalize_core_payload,
)


def test_hashes_mutation_does_not_affect_core_canonicalization() -> None:
    record = DecisionRecord(
        decision_id="dec-hash",
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
        selection=Selection(
            selected=True,
            strategy_id="TREND_FOLLOW",
            status="selected",
            score=None,
            reasons=["r1"],
            rules_fired=["R1"],
        ),
        outcome=Outcome(decision="SELECT", allowed=True, notes=None),
    )

    payload = record.to_dict()
    payload["hashes"]["core_hash"] = "sha256:deadbeef"
    payload["hashes"]["content_hash"] = "sha256:deadbeef"

    assert canonicalize_core_payload(payload) == record.canonicalize_core()

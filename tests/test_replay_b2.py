from __future__ import annotations

import json
from pathlib import Path

from audit.decision_records import DecisionRecordWriter
from audit.replay import replay_verify
from selector.selector import select_strategy


def test_replay_all_matched(tmp_path: Path) -> None:
    out_path = tmp_path / "decision_records.jsonl"
    writer = DecisionRecordWriter(out_path=str(out_path), run_id="test_run")
    select_strategy(
        market_state={"trend_state": "UP"},
        risk_state="GREEN",
        timeframe="1m",
        record_writer=writer,
    )
    select_strategy(
        market_state={"trend_state": "RANGE", "volatility_regime": "LOW"},
        risk_state="GREEN",
        timeframe="1m",
        record_writer=writer,
    )
    writer.close()

    result = replay_verify(records_path=str(out_path))
    assert result.total == 2
    assert result.mismatched == 0
    assert result.hash_mismatch == 0
    assert result.errors == 0


def test_replay_detects_hash_mismatch(tmp_path: Path) -> None:
    out_path = tmp_path / "decision_records.jsonl"
    writer = DecisionRecordWriter(out_path=str(out_path), run_id="test_run")
    writer.append(
        timeframe="1m",
        risk_state="GREEN",
        market_state={"trend_state": "UP"},
        selection={"strategy_id": "trend_follow_v1_conservative", "engine_id": "trend", "reason": []},
    )
    writer.close()

    lines = out_path.read_text(encoding="utf-8").splitlines()
    loaded = json.loads(lines[0])
    loaded["market_state_hash"] = "sha256:deadbeef"
    out_path.write_text(json.dumps(loaded) + "\n", encoding="utf-8")

    result = replay_verify(records_path=str(out_path))
    assert result.hash_mismatch == 1
    assert result.matched == 0


def test_replay_detects_selection_mismatch(tmp_path: Path) -> None:
    out_path = tmp_path / "decision_records.jsonl"
    writer = DecisionRecordWriter(out_path=str(out_path), run_id="test_run")
    writer.append(
        timeframe="1m",
        risk_state="GREEN",
        market_state={"trend_state": "UP"},
        selection={"strategy_id": "trend_follow_v1_conservative", "engine_id": "trend", "reason": []},
    )
    writer.close()

    lines = out_path.read_text(encoding="utf-8").splitlines()
    loaded = json.loads(lines[0])
    loaded["selection"]["strategy_id"] = "NONE"
    out_path.write_text(json.dumps(loaded) + "\n", encoding="utf-8")

    result = replay_verify(records_path=str(out_path))
    assert result.mismatched == 1

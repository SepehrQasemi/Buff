from __future__ import annotations

import json
from pathlib import Path

from audit.decision_records import DecisionRecordWriter, infer_next_seq_from_jsonl
from audit.faults import truncate_file_mid_line, write_corrupted_jsonl
from audit.replay import load_decision_records, replay_verify, last_load_errors
from selector.selector import select_strategy


def test_load_decision_records_tolerates_corruption(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.jsonl"
    write_corrupted_jsonl(str(path))

    records = load_decision_records(str(path))
    assert len(records) >= 2
    assert last_load_errors() >= 2


def test_replay_verify_skips_corrupted_lines(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.jsonl"
    write_corrupted_jsonl(str(path))

    result = replay_verify(records_path=str(path))
    assert result.total >= 2
    assert result.errors >= 1


def test_infer_next_seq_restart_safe(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    writer = DecisionRecordWriter(out_path=str(path), run_id="test_run")
    writer.append(
        timeframe="1m",
        risk_state="GREEN",
        market_state={"trend_state": "UP"},
        selection={"strategy_id": "trend_follow_v1_conservative", "engine_id": "trend", "reason": []},
    )
    writer.append(
        timeframe="1m",
        risk_state="GREEN",
        market_state={"trend_state": "DOWN"},
        selection={"strategy_id": "trend_follow_v1_short", "engine_id": "trend", "reason": []},
    )
    writer.append(
        timeframe="1m",
        risk_state="GREEN",
        market_state={"trend_state": "UP"},
        selection={"strategy_id": "trend_follow_v1_conservative", "engine_id": "trend", "reason": []},
    )
    writer.close()

    truncate_file_mid_line(str(path))
    next_seq = infer_next_seq_from_jsonl(str(path))
    assert next_seq == 2

    writer = DecisionRecordWriter(out_path=str(path), run_id="test_run", start_seq=next_seq)
    record = writer.append(
        timeframe="1m",
        risk_state="GREEN",
        market_state={"trend_state": "UP"},
        selection={"strategy_id": "trend_follow_v1_conservative", "engine_id": "trend", "reason": []},
    )
    writer.close()

    lines = path.read_text(encoding="utf-8").splitlines()
    loaded = None
    for line in reversed(lines):
        try:
            loaded = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    assert loaded is not None
    assert loaded["seq"] == next_seq
    assert record.seq == next_seq


def test_selector_handles_missing_market_state_keys(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    writer = DecisionRecordWriter(out_path=str(path), run_id="test_run")
    result = select_strategy(
        market_state={},
        risk_state="GREEN",
        timeframe="1m",
        record_writer=writer,
    )
    writer.close()

    assert result["strategy_id"] == "NONE"
    replay_result = replay_verify(records_path=str(path))
    assert replay_result.mismatched == 0

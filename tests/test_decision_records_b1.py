from __future__ import annotations

import json
from pathlib import Path

from audit.decision_records import DecisionRecordWriter, canonical_json, ensure_run_dir, sha256_hex
from risk.types import RiskState
from selector.records import selection_to_record
from selector.selector import select_strategy


def test_canonical_json_deterministic() -> None:
    d1 = {"b": 1, "a": 2}
    d2 = {"a": 2, "b": 1}
    assert canonical_json(d1) == canonical_json(d2)


def test_market_state_hash_deterministic() -> None:
    d1 = {"b": 1, "a": 2}
    d2 = {"a": 2, "b": 1}
    assert sha256_hex(canonical_json(d1)) == sha256_hex(canonical_json(d2))


def test_writer_appends_jsonl(tmp_path: Path) -> None:
    out_path = tmp_path / "decision_records.jsonl"
    writer = DecisionRecordWriter(out_path=str(out_path), run_id="test_run")
    writer.append(
        timeframe="1m",
        risk_state="GREEN",
        market_state={
            "trend_state": "up",
            "volatility_regime": "low",
            "momentum_state": "neutral",
            "structure_state": "breakout",
        },
        selection={
            "strategy_id": "TREND_FOLLOW",
            "rule_id": "R2",
            "reason": "trend+breakout & vol not high",
            "inputs": {
                "risk_state": "GREEN",
                "trend_state": "up",
                "volatility_regime": "low",
                "structure_state": "breakout",
            },
        },
    )
    writer.append(
        timeframe="1m",
        risk_state="GREEN",
        market_state={
            "trend_state": "up",
            "volatility_regime": "low",
            "momentum_state": "neutral",
            "structure_state": "breakout",
        },
        selection={
            "strategy_id": "TREND_FOLLOW",
            "rule_id": "R2",
            "reason": "trend+breakout & vol not high",
            "inputs": {
                "risk_state": "GREEN",
                "trend_state": "up",
                "volatility_regime": "low",
                "structure_state": "breakout",
            },
        },
    )
    writer.close()

    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    records = [json.loads(line) for line in lines]
    assert [record["seq"] for record in records] == [0, 1]
    assert all(record["run_id"] == "test_run" for record in records)
    assert all(record["schema_version"] == "dr.v1" for record in records)
    assert all(record["market_state_hash"].startswith("sha256:") for record in records)


def test_selector_logs_when_writer_provided(tmp_path: Path) -> None:
    out_path = Path(ensure_run_dir("test_run"))
    out_path = tmp_path / out_path.name
    writer = DecisionRecordWriter(out_path=str(out_path), run_id="test_run")
    signals = {
        "trend_state": "up",
        "volatility_regime": "low",
        "momentum_state": "neutral",
        "structure_state": "breakout",
    }
    result = select_strategy(signals, RiskState.GREEN)
    writer.append(
        timeframe="1m",
        risk_state=RiskState.GREEN.value,
        market_state=signals,
        selection=selection_to_record(result),
    )
    writer.close()

    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["selection"]["strategy_id"] == result.strategy_id

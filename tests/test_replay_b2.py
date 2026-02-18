from __future__ import annotations

import json
from pathlib import Path

from audit.decision_records import DecisionRecordWriter
from audit.replay import replay_verify
from risk.contracts import RiskState
from selector.records import selection_to_record
from selector.selector import select_strategy


def test_replay_all_matched(tmp_path: Path) -> None:
    out_path = tmp_path / "decision_records.jsonl"
    writer = DecisionRecordWriter(out_path=str(out_path), run_id="test_run")
    signals_a = {
        "trend_state": "up",
        "volatility_regime": "low",
        "momentum_state": "neutral",
        "structure_state": "breakout",
    }
    signals_b = {
        "trend_state": "flat",
        "volatility_regime": "mid",
        "momentum_state": "neutral",
        "structure_state": "meanrevert",
    }
    selection_a = select_strategy(signals_a, RiskState.GREEN)
    selection_b = select_strategy(signals_b, RiskState.GREEN)
    writer.append(
        timeframe="1m",
        risk_state=RiskState.GREEN.value,
        market_state=signals_a,
        selection=selection_to_record(selection_a),
    )
    writer.append(
        timeframe="1m",
        risk_state=RiskState.GREEN.value,
        market_state=signals_b,
        selection=selection_to_record(selection_b),
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
    loaded = json.loads(lines[0])
    loaded["selection"]["strategy_id"] = "MEAN_REVERT"
    out_path.write_text(json.dumps(loaded) + "\n", encoding="utf-8")

    result = replay_verify(records_path=str(out_path))
    assert result.mismatched == 1

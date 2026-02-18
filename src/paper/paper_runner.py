from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from audit.decision_records import DecisionRecordWriter, ensure_run_dir, infer_next_seq_from_jsonl
from audit.replay import replay_verify
from risk.contracts import RiskState
from selector.records import selection_to_record
from selector.selector import select_strategy
from selector.types import MarketSignals


@dataclass(frozen=True)
class PaperRunConfig:
    run_id: str
    timeframe: str = "1m"
    steps: int = 200
    restart_every: int = 50
    out_dir: str = "runs"


def generate_mock_market_state(i: int) -> MarketSignals:
    if i % 4 == 0:
        return {
            "trend_state": "up",
            "volatility_regime": "low",
            "momentum_state": "bull",
            "structure_state": "breakout",
        }
    if i % 4 == 1:
        return {
            "trend_state": "down",
            "volatility_regime": "mid",
            "momentum_state": "bear",
            "structure_state": "breakout",
        }
    if i % 4 == 2:
        return {
            "trend_state": "flat",
            "volatility_regime": "low",
            "momentum_state": "neutral",
            "structure_state": "meanrevert",
        }
    return {
        "trend_state": "unknown",
        "volatility_regime": "high",
        "momentum_state": "unknown",
        "structure_state": "none",
    }


def _writer_for_run(run_id: str, out_dir: str) -> tuple[DecisionRecordWriter, str]:
    base = Path(out_dir)
    base.mkdir(parents=True, exist_ok=True)
    cwd = Path.cwd()
    try:
        os.chdir(base)
        records_path = str(Path(ensure_run_dir(run_id)).resolve())
    finally:
        os.chdir(cwd)
    next_seq = infer_next_seq_from_jsonl(records_path)
    writer = DecisionRecordWriter(out_path=records_path, run_id=run_id, start_seq=next_seq)
    return writer, records_path


def run_paper_smoke(config: PaperRunConfig) -> dict:
    writer, records_path = _writer_for_run(config.run_id, config.out_dir)

    for step in range(config.steps):
        market_state = generate_mock_market_state(step)
        if step % 10 == 0:
            risk_state = RiskState.RED
        elif step % 5 == 0:
            risk_state = RiskState.YELLOW
        else:
            risk_state = RiskState.GREEN

        selection = select_strategy(market_state, risk_state)
        writer.append(
            timeframe=config.timeframe,
            risk_state=risk_state.value,
            market_state=market_state,
            selection=selection_to_record(selection),
        )

        if config.restart_every > 0 and (step + 1) % config.restart_every == 0:
            writer.close()
            writer, records_path = _writer_for_run(config.run_id, config.out_dir)

    writer.close()

    replay_result = replay_verify(records_path=records_path)
    if replay_result.mismatched > 0 or replay_result.hash_mismatch > 0:
        raise RuntimeError("replay_verification_failed")

    return {
        "records_path": records_path,
        "total": replay_result.total,
        "matched": replay_result.matched,
        "mismatched": replay_result.mismatched,
        "hash_mismatch": replay_result.hash_mismatch,
        "errors": replay_result.errors,
    }

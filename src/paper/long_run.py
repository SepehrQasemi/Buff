from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from audit.decision_records import (
    DecisionRecordWriter,
    infer_next_seq_from_jsonl,
    infer_next_shard_and_seq,
    make_records_path,
)
from audit.replay import replay_verify
from paper.market_state_feed import cycling_feed, load_market_state_feed
from paper.paper_runner import generate_mock_market_state
from selector.selector import select_strategy


@dataclass(frozen=True)
class LongRunConfig:
    run_id: str
    timeframe: str = "1m"
    duration_seconds: int = 3600
    restart_every_seconds: int = 300
    rotate_every_records: int = 5000
    replay_every_records: int = 2000
    out_dir: str = "runs"
    feed_path: str | None = None


def _risk_state(step: int) -> str:
    if step % 10 == 0:
        return "RED"
    if step % 5 == 0:
        return "YELLOW"
    return "GREEN"


def _resolve_run_dir(run_id: str, out_dir: str) -> Path:
    base = Path(out_dir)
    run_dir = base / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _writer_for_shard(run_id: str, shard_index: int, start_seq: int, out_dir: str) -> DecisionRecordWriter:
    base = Path(out_dir)
    base.mkdir(parents=True, exist_ok=True)
    cwd = Path.cwd()
    try:
        os.chdir(base)
        _ = make_records_path(run_id, shard_index=shard_index)
    finally:
        os.chdir(cwd)
    records_path = (base / "runs" / run_id / f"decision_records_{shard_index:04d}.jsonl").resolve()
    return DecisionRecordWriter(out_path=str(records_path), run_id=run_id, start_seq=start_seq)


def _list_shards(run_dir: Path) -> list[Path]:
    return sorted(run_dir.glob("decision_records_*.jsonl"))


def _replay_all_shards(run_dir: Path) -> dict:
    totals = {"total": 0, "matched": 0, "mismatched": 0, "hash_mismatch": 0, "errors": 0}
    for shard in _list_shards(run_dir):
        result = replay_verify(records_path=str(shard))
        totals["total"] += result.total
        totals["matched"] += result.matched
        totals["mismatched"] += result.mismatched
        totals["hash_mismatch"] += result.hash_mismatch
        totals["errors"] += result.errors
    return totals


def run_long_paper(config: LongRunConfig) -> dict:
    run_dir = _resolve_run_dir(config.run_id, config.out_dir)
    shard_index, next_seq = infer_next_shard_and_seq(str(run_dir))
    writer = _writer_for_shard(config.run_id, shard_index, next_seq, config.out_dir)

    feed_errors = 0
    feed_iter = None
    if config.feed_path is not None:
        feed = load_market_state_feed(config.feed_path)
        feed_errors = feed.errors
        feed_iter = cycling_feed(iter(feed))

    start_ts = time.time()
    last_restart = start_ts
    step = 0
    records_written = 0

    while time.time() - start_ts < config.duration_seconds:
        if feed_iter is not None:
            market_state = next(feed_iter)
        else:
            market_state = generate_mock_market_state(step)
        risk_state = _risk_state(step)
        select_strategy(
            market_state=market_state,
            risk_state=risk_state,
            timeframe=config.timeframe,
            record_writer=writer,
        )
        step += 1
        records_written += 1

        if config.rotate_every_records > 0 and records_written % config.rotate_every_records == 0:
            writer.close()
            records_path = run_dir / f"decision_records_{shard_index:04d}.jsonl"
            next_seq = infer_next_seq_from_jsonl(str(records_path))
            shard_index += 1
            writer = _writer_for_shard(config.run_id, shard_index, next_seq, config.out_dir)

        if config.replay_every_records > 0 and records_written % config.replay_every_records == 0:
            writer.close()
            totals = _replay_all_shards(run_dir)
            if totals["mismatched"] > 0 or totals["hash_mismatch"] > 0:
                raise RuntimeError("replay_verification_failed")
            shard_index, next_seq = infer_next_shard_and_seq(str(run_dir))
            writer = _writer_for_shard(config.run_id, shard_index, next_seq, config.out_dir)

        if config.restart_every_seconds > 0 and time.time() - last_restart >= config.restart_every_seconds:
            writer.close()
            shard_index, next_seq = infer_next_shard_and_seq(str(run_dir))
            writer = _writer_for_shard(config.run_id, shard_index, next_seq, config.out_dir)
            last_restart = time.time()

    writer.close()
    totals = _replay_all_shards(run_dir)
    if totals["mismatched"] > 0 or totals["hash_mismatch"] > 0:
        raise RuntimeError("replay_verification_failed")

    totals["records_path"] = str(run_dir)
    totals["shards"] = len(_list_shards(run_dir))
    totals["feed_errors"] = feed_errors
    return totals

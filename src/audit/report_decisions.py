from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from audit.replay import replay_verify


def _iter_records(run_dir: Path) -> list[dict]:
    records: list[dict] = []
    for shard in sorted(run_dir.glob("decision_records_*.jsonl")):
        for line in shard.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def build_summary(run_dir: Path) -> dict:
    records = _iter_records(run_dir)
    shards = list(run_dir.glob("decision_records_*.jsonl"))
    risk_counts: Counter[str] = Counter()
    strategy_counts: Counter[str] = Counter()
    none_count = 0
    ts_values: list[str] = []

    for record in records:
        risk_state = record.get("risk_state", "")
        risk_counts[risk_state] += 1
        selection = record.get("selection", {})
        strategy_id = selection.get("strategy_id")
        if strategy_id is None:
            continue
        strategy_counts[strategy_id] += 1
        if strategy_id == "NONE":
            none_count += 1
        ts = record.get("ts_utc")
        if isinstance(ts, str):
            ts_values.append(ts)

    replay_totals = {
        "total": 0,
        "matched": 0,
        "mismatched": 0,
        "hash_mismatch": 0,
        "errors": 0,
    }
    for shard in sorted(shards):
        result = replay_verify(records_path=str(shard))
        replay_totals["total"] += result.total
        replay_totals["matched"] += result.matched
        replay_totals["mismatched"] += result.mismatched
        replay_totals["hash_mismatch"] += result.hash_mismatch
        replay_totals["errors"] += result.errors

    summary = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_records": len(records),
        "shards_count": len(shards),
        "risk_state_counts": dict(risk_counts),
        "strategy_id_counts": dict(strategy_counts),
        "none_count": none_count,
        "first_ts": min(ts_values) if ts_values else None,
        "last_ts": max(ts_values) if ts_values else None,
        "replay_verification": replay_totals,
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize decision_records shards.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    out_path = Path(args.out)
    summary = build_summary(run_dir)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

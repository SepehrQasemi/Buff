from __future__ import annotations

from pathlib import Path

from paper.long_run import LongRunConfig, run_long_paper


def test_long_run_short_smoke(tmp_path: Path) -> None:
    config = LongRunConfig(
        run_id="longrun",
        duration_seconds=2,
        restart_every_seconds=1,
        rotate_every_records=10,
        replay_every_records=7,
        out_dir=str(tmp_path),
    )
    summary = run_long_paper(config)
    run_dir = Path(summary["records_path"])
    assert run_dir.exists()
    assert summary["mismatched"] == 0
    assert summary["hash_mismatch"] == 0
    assert summary["shards"] >= 1


def test_rotation_creates_multiple_shards(tmp_path: Path) -> None:
    config = LongRunConfig(
        run_id="rotate",
        duration_seconds=2,
        restart_every_seconds=1,
        rotate_every_records=5,
        replay_every_records=50,
        out_dir=str(tmp_path),
    )
    summary = run_long_paper(config)
    run_dir = Path(summary["records_path"])
    shards = list(run_dir.glob("decision_records_*.jsonl"))
    assert len(shards) >= 2

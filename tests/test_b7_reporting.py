from __future__ import annotations

from pathlib import Path

from audit.report_decisions import build_summary
from paper.feed_generate import write_feed
from paper.long_run import LongRunConfig, run_long_paper


def test_feed_generate_deterministic(tmp_path: Path) -> None:
    path_a = tmp_path / "feed_a.jsonl"
    path_b = tmp_path / "feed_b.jsonl"
    write_feed(path_a, rows=1000, seed=42)
    write_feed(path_b, rows=1000, seed=42)
    assert path_a.read_bytes() == path_b.read_bytes()


def test_report_decisions_counts(tmp_path: Path) -> None:
    config = LongRunConfig(
        run_id="reporting",
        duration_seconds=2,
        restart_every_seconds=1,
        rotate_every_records=10,
        replay_every_records=7,
        out_dir=str(tmp_path),
    )
    summary = run_long_paper(config)
    run_dir = Path(summary["records_path"])
    report = build_summary(run_dir)
    assert report["total_records"] > 0
    assert report["strategy_id_counts"]

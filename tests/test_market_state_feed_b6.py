from __future__ import annotations

import json
from pathlib import Path

from paper.long_run import LongRunConfig, run_long_paper
from paper.market_state_feed import load_market_state_feed


def test_feed_skips_corrupt_lines(tmp_path: Path) -> None:
    path = tmp_path / "feed.jsonl"
    lines = [
        json.dumps({"trend_state": "UP"}),
        "{bad json",
        json.dumps(123),
        json.dumps({"trend_state": "RANGE", "volatility_regime": "LOW"}),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    feed = load_market_state_feed(str(path))
    assert len(feed.items) == 2


def test_long_run_with_feed(tmp_path: Path) -> None:
    path = tmp_path / "feed.jsonl"
    lines = [
        json.dumps({"trend_state": "UP"}),
        json.dumps({"trend_state": "DOWN"}),
        json.dumps({"trend_state": "RANGE", "volatility_regime": "LOW"}),
        json.dumps({"volatility_regime": "HIGH", "momentum_state": "SPIKE"}),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    config = LongRunConfig(
        run_id="feedrun",
        duration_seconds=2,
        restart_every_seconds=1,
        rotate_every_records=10,
        replay_every_records=7,
        out_dir=str(tmp_path),
        feed_path=str(path),
    )
    summary = run_long_paper(config)
    assert summary["mismatched"] == 0
    assert summary["hash_mismatch"] == 0
    run_dir = Path(summary["records_path"])
    assert list(run_dir.glob("decision_records_*.jsonl"))

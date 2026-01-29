from __future__ import annotations

import json
from pathlib import Path

from paper.paper_runner import PaperRunConfig, run_paper_smoke


def _load_valid_records(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def test_paper_smoke_end_to_end(tmp_path: Path) -> None:
    config = PaperRunConfig(
        run_id="smoke",
        steps=40,
        restart_every=10,
        out_dir=str(tmp_path),
    )
    summary = run_paper_smoke(config)
    records_path = Path(summary["records_path"])
    assert records_path.exists()
    assert summary["mismatched"] == 0
    assert summary["hash_mismatch"] == 0
    assert len(_load_valid_records(records_path)) >= config.steps


def test_paper_restart_continues_seq(tmp_path: Path) -> None:
    config = PaperRunConfig(
        run_id="seqtest",
        steps=25,
        restart_every=5,
        out_dir=str(tmp_path),
    )
    summary = run_paper_smoke(config)
    records_path = Path(summary["records_path"])
    records = _load_valid_records(records_path)
    seqs = [record["seq"] for record in records]
    assert seqs[0] == 0
    assert all(seqs[i] <= seqs[i + 1] for i in range(len(seqs) - 1))
    assert len(seqs) == config.steps

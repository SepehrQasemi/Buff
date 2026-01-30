from __future__ import annotations

import json
from pathlib import Path

from decision_records.schema import SCHEMA_VERSION
from workspaces.indexer import build_index, list_run_dirs, write_index


def _record(run_id: str, ts: str, status: str, risk: str, reason: str | None = None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "timestamp_utc": ts,
        "environment": "PAPER",
        "control_status": "ARMED",
        "strategy": {"name": "dummy", "version": "1.0.0"},
        "risk_status": risk,
        "execution_status": status,
        "reason": reason,
        "inputs_digest": "sha256:deadbeef",
        "artifact_paths": {"decision_records": f"workspaces/{run_id}/decision_records.jsonl"},
    }


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_write_index_deterministic(tmp_path: Path) -> None:
    workspaces_dir = tmp_path / "workspaces"
    run_a = workspaces_dir / "runA"
    run_b = workspaces_dir / "runB"
    run_c = workspaces_dir / "runC"
    run_d = workspaces_dir / "runD"
    run_a.mkdir(parents=True)
    run_b.mkdir(parents=True)
    run_c.mkdir(parents=True)
    run_d.mkdir(parents=True)

    records_a = [
        _record("runA", "2024-01-01T00:00:00.000Z", "EXECUTED", "GREEN"),
        _record("runA", "2024-01-01T00:01:00.000Z", "BLOCKED", "RED", "risk_veto"),
    ]
    (run_a / "decision_records.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records_a) + "\n", encoding="utf-8"
    )

    summary_b = {
        "schema_version": SCHEMA_VERSION,
        "total": 1,
        "executed": 1,
        "blocked": 0,
        "error": 0,
        "first_timestamp_utc": "2024-01-01T00:00:00.000Z",
        "last_timestamp_utc": "2024-01-01T00:00:00.000Z",
        "risk_status_counts": {"GREEN": 1},
        "execution_status_counts": {"EXECUTED": 1},
        "strategy_counts": {"dummy": 1},
    }
    _write_json(run_b / "report_summary.json", summary_b)

    (run_d / "report_summary.json").write_text("{bad json", encoding="utf-8")

    outputs = write_index(workspaces_dir)
    index_json = Path(outputs["index_json"]).read_text(encoding="utf-8")
    index_md = Path(outputs["index_md"]).read_text(encoding="utf-8")

    outputs2 = write_index(workspaces_dir)
    index_json2 = Path(outputs2["index_json"]).read_text(encoding="utf-8")
    index_md2 = Path(outputs2["index_md"]).read_text(encoding="utf-8")

    assert index_json == index_json2
    assert index_md == index_md2

    index = json.loads(index_json)
    runs = [run["run_id"] for run in index["runs"]]
    assert runs == sorted(runs)


def test_list_run_dirs_sorted(tmp_path: Path) -> None:
    workspaces_dir = tmp_path / "workspaces"
    (workspaces_dir / "b").mkdir(parents=True)
    (workspaces_dir / "a").mkdir(parents=True)
    (workspaces_dir / "c").mkdir(parents=True)

    runs = list_run_dirs(workspaces_dir)
    assert [run.name for run in runs] == ["a", "b", "c"]


def test_build_index_statuses(tmp_path: Path) -> None:
    workspaces_dir = tmp_path / "workspaces"
    run_empty = workspaces_dir / "runC"
    run_empty.mkdir(parents=True)

    index = build_index(workspaces_dir)
    assert index["runs"][0]["status"] == "empty"

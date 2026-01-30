from __future__ import annotations

import json
from pathlib import Path

from chatbot.artifacts import get_run_artifacts, list_runs


def _write_index(path: Path, runs: list[dict]) -> None:
    payload = {"schema_version": "1.0", "generated_at_utc": "N/A", "runs": runs}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_unknown_run_returns_empty_paths(tmp_path: Path) -> None:
    workspaces = tmp_path / "workspaces"
    _write_index(workspaces / "index.json", [{"run_id": "runA", "status": "ok"}])

    result = get_run_artifacts("missing", workspaces)

    assert result["status"] == "unknown"
    assert result["decision_records"] == ""
    assert result["report_md"] == ""
    assert result["report_summary"] == ""
    assert result["index"] == "workspaces/index.json"


def test_known_run_with_full_artifacts(tmp_path: Path) -> None:
    workspaces = tmp_path / "workspaces"
    run_dir = workspaces / "runA"
    run_dir.mkdir(parents=True)
    (run_dir / "decision_records.jsonl").write_text("{}\n", encoding="utf-8")
    (run_dir / "report.md").write_text("# Report\n", encoding="utf-8")
    (run_dir / "report_summary.json").write_text("{}", encoding="utf-8")

    _write_index(workspaces / "index.json", [{"run_id": "runA", "status": "ok"}])

    result = get_run_artifacts("runA", workspaces)

    assert result["status"] == "ok"
    assert result["decision_records"] == "workspaces/runA/decision_records.jsonl"
    assert result["report_md"] == "workspaces/runA/report.md"
    assert result["report_summary"] == "workspaces/runA/report_summary.json"
    assert result["index"] == "workspaces/index.json"


def test_known_run_with_partial_artifacts(tmp_path: Path) -> None:
    workspaces = tmp_path / "workspaces"
    run_dir = workspaces / "runB"
    run_dir.mkdir(parents=True)
    (run_dir / "decision_records.jsonl").write_text("{}\n", encoding="utf-8")

    _write_index(workspaces / "index.json", [{"run_id": "runB", "status": "ok"}])

    result = get_run_artifacts("runB", workspaces)

    assert result["decision_records"] == "workspaces/runB/decision_records.jsonl"
    assert result["report_md"] == ""
    assert result["report_summary"] == ""


def test_list_runs_deterministic(tmp_path: Path) -> None:
    workspaces = tmp_path / "workspaces"
    _write_index(
        workspaces / "index.json",
        [
            {"run_id": "runC", "status": "ok"},
            {"run_id": "runA", "status": "ok"},
            {"run_id": "runB", "status": "ok"},
        ],
    )

    assert list_runs(workspaces) == ["runA", "runB", "runC"]
    assert list_runs(workspaces) == ["runA", "runB", "runC"]

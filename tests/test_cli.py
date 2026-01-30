from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write_index(path: Path, runs: list[dict]) -> None:
    payload = {"schema_version": "1.0", "generated_at_utc": "N/A", "runs": runs}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _write_decision_record(run_dir: Path, run_id: str) -> None:
    record = {
        "schema_version": "1.0",
        "run_id": run_id,
        "timestamp_utc": "2024-01-01T00:00:00Z",
        "environment": "PAPER",
        "control_status": "ARMED",
        "strategy": {"name": "demo", "version": "1"},
        "risk_status": "GREEN",
        "execution_status": "EXECUTED",
        "reason": None,
        "inputs_digest": "sha256:demo",
        "artifact_paths": {
            "decision_records": f"workspaces/{run_id}/decision_records.jsonl",
        },
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "decision_records.jsonl").write_text(
        json.dumps(record, sort_keys=True) + "\n", encoding="utf-8"
    )


def _run_cli(args: list[str], workspaces: Path) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "src.cli", "--workspaces", str(workspaces)] + args
    return subprocess.run(cmd, capture_output=True, text=True)


def test_cli_list_runs(tmp_path: Path) -> None:
    workspaces = tmp_path / "workspaces"
    _write_index(
        workspaces / "index.json",
        [
            {"run_id": "runC", "status": "ok"},
            {"run_id": "runA", "status": "ok"},
            {"run_id": "runB", "status": "ok"},
        ],
    )

    result = _run_cli(["list-runs"], workspaces)

    assert result.returncode == 0
    assert result.stdout.strip().splitlines() == ["runA", "runB", "runC"]


def test_cli_show(tmp_path: Path) -> None:
    workspaces = tmp_path / "workspaces"
    run_id = "demo"
    run_dir = workspaces / run_id
    _write_decision_record(run_dir, run_id)
    (run_dir / "report.md").write_text("# Report\n", encoding="utf-8")
    (run_dir / "report_summary.json").write_text("{}", encoding="utf-8")
    _write_index(workspaces / "index.json", [{"run_id": run_id, "status": "ok"}])

    result = _run_cli(["show", "--run-id", run_id], workspaces)

    assert result.returncode == 0
    lines = result.stdout.strip().splitlines()
    assert lines == [
        f"workspaces/{run_id}/decision_records.jsonl",
        f"workspaces/{run_id}/report.md",
        f"workspaces/{run_id}/report_summary.json",
        "workspaces/index.json",
    ]


def test_cli_index_and_report(tmp_path: Path) -> None:
    workspaces = tmp_path / "workspaces"
    run_id = "demo"
    run_dir = workspaces / run_id
    _write_decision_record(run_dir, run_id)

    result_index = _run_cli(["index"], workspaces)

    assert result_index.returncode == 0
    index_paths = result_index.stdout.strip().splitlines()
    assert (workspaces / "index.json").exists()
    assert (workspaces / "index.md").exists()
    assert index_paths[0].endswith("index.json")
    assert index_paths[1].endswith("index.md")

    result_report = _run_cli(["report", "--run-id", run_id], workspaces)

    assert result_report.returncode == 0
    report_paths = result_report.stdout.strip().splitlines()
    assert (workspaces / run_id / "report.md").exists()
    assert (workspaces / run_id / "report_summary.json").exists()
    assert report_paths[0].endswith("report.md")
    assert report_paths[1].endswith("report_summary.json")


def test_cli_validate_run(tmp_path: Path) -> None:
    workspaces = tmp_path / "workspaces"
    run_id = "demo"
    _write_decision_record(workspaces / run_id, run_id)

    result = _run_cli(["validate-run", "--run-id", run_id], workspaces)

    assert result.returncode == 0
    assert result.stdout.strip() == "valid"


def test_cli_invalid_run_id_fails(tmp_path: Path) -> None:
    workspaces = tmp_path / "workspaces"
    _write_index(workspaces / "index.json", [])

    result = _run_cli(["report", "--run-id", "../bad"], workspaces)

    assert result.returncode != 0

from __future__ import annotations

import json
from pathlib import Path

import pytest

from decision_records.schema import SCHEMA_VERSION
from reports.decision_report import (
    load_decision_records,
    render_markdown,
    summarize_records,
    write_report,
)


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


def test_report_generation_deterministic(tmp_path: Path) -> None:
    run_id = "run1"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    records_path = run_dir / "decision_records.jsonl"

    records = [
        _record(run_id, "2024-01-01T00:00:00.000Z", "EXECUTED", "GREEN"),
        _record(run_id, "2024-01-01T00:01:00.000Z", "BLOCKED", "RED", "risk_veto"),
        _record(run_id, "2024-01-01T00:02:00.000Z", "EXECUTED", "GREEN"),
        _record(run_id, "2024-01-01T00:03:00.000Z", "ERROR", "RED", "engine_error"),
    ]
    records_path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

    outputs = write_report(tmp_path, run_id, last_n=10)
    assert Path(outputs["report_md"]).exists()
    assert Path(outputs["report_summary"]).exists()

    summary = json.loads(Path(outputs["report_summary"]).read_text(encoding="utf-8"))
    assert summary["total"] == 4
    assert summary["executed"] == 2
    assert summary["blocked"] == 1
    assert summary["error"] == 1

    markdown = Path(outputs["report_md"]).read_text(encoding="utf-8")
    assert "Decision Report" in markdown
    assert "Summary" in markdown
    assert "Last 4 Decisions" in markdown

    outputs2 = write_report(tmp_path, run_id, last_n=10)
    markdown2 = Path(outputs2["report_md"]).read_text(encoding="utf-8")
    assert markdown == markdown2


def test_invalid_json_line_raises(tmp_path: Path) -> None:
    run_id = "run2"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    records_path = run_dir / "decision_records.jsonl"
    records_path.write_text("{bad json\n", encoding="utf-8")

    with pytest.raises(ValueError):
        write_report(tmp_path, run_id)

    assert not (run_dir / "report.md").exists()
    assert not (run_dir / "report_summary.json").exists()


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        write_report(tmp_path, "missing")


def test_load_and_render_helpers(tmp_path: Path) -> None:
    run_id = "run3"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    records_path = run_dir / "decision_records.jsonl"
    records = [_record(run_id, "2024-01-01T00:00:00.000Z", "EXECUTED", "GREEN")]
    records_path.write_text(json.dumps(records[0]) + "\n", encoding="utf-8")

    loaded = load_decision_records(records_path)
    summary = summarize_records(loaded)
    markdown = render_markdown(summary, loaded, last_n=5)

    assert summary["total"] == 1
    assert "Artifacts" in markdown

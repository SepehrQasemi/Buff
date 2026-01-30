from __future__ import annotations

import json
from pathlib import Path


def _write_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True))
        handle.write("\n")


def make_workspace(tmp_path: Path, runs: dict[str, str]) -> Path:
    workspaces = tmp_path / "workspaces"
    for run_id, kind in runs.items():
        run_dir = workspaces / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        if kind == "empty":
            continue

        records_path = run_dir / "decision_records.jsonl"
        if kind == "invalid":
            _write_record(records_path, {"schema_version": "1.0", "run_id": run_id})
            continue

        if kind != "ok":
            raise ValueError(f"unknown_fixture_kind:{kind}")

        executed = {
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
        blocked = {
            "schema_version": "1.0",
            "run_id": run_id,
            "timestamp_utc": "2024-01-01T00:01:00Z",
            "environment": "PAPER",
            "control_status": "ARMED",
            "strategy": {"name": "demo", "version": "1"},
            "risk_status": "RED",
            "execution_status": "BLOCKED",
            "reason": "risk_veto",
            "inputs_digest": "sha256:demo2",
            "artifact_paths": {
                "decision_records": f"workspaces/{run_id}/decision_records.jsonl",
            },
        }
        _write_record(records_path, executed)
        _write_record(records_path, blocked)

    return workspaces

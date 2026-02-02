from __future__ import annotations

import json
from pathlib import Path

import pytest

from audit.workspace_snapshot import (
    WorkspaceSnapshotError,
    create_workspace_manifest,
    verify_workspace_manifest,
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_manifest_detects_hash_mismatch(tmp_path: Path) -> None:
    workspaces = tmp_path / "workspaces"
    run_dir = workspaces / "run-1"
    run_dir.mkdir(parents=True, exist_ok=True)

    _write_json(run_dir / "report_summary.json", {"run_id": "run-1", "status": "ok"})
    records = run_dir / "decision_records.jsonl"
    records.write_text('{"seq":0}\n', encoding="utf-8")

    manifest_path = create_workspace_manifest(run_dir)

    with records.open("ab") as handle:
        handle.write(b"x")

    with pytest.raises(WorkspaceSnapshotError) as excinfo:
        verify_workspace_manifest(manifest_path)
    assert excinfo.value.reason == "hash_mismatch"


def test_manifest_detects_missing_file(tmp_path: Path) -> None:
    workspaces = tmp_path / "workspaces"
    run_dir = workspaces / "run-2"
    run_dir.mkdir(parents=True, exist_ok=True)

    _write_json(run_dir / "report_summary.json", {"run_id": "run-2", "status": "ok"})
    records = run_dir / "decision_records.jsonl"
    records.write_text('{"seq":0}\n', encoding="utf-8")

    manifest_path = create_workspace_manifest(run_dir)
    records.unlink()

    with pytest.raises(WorkspaceSnapshotError) as excinfo:
        verify_workspace_manifest(manifest_path)
    assert excinfo.value.reason == "missing_file"

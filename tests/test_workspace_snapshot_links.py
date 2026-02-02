from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from audit.workspace_snapshot import materialize_workspace_snapshot


pytestmark = pytest.mark.unit


def _write_text(path: Path, payload: str) -> None:
    path.write_text(payload, encoding="utf-8")


def _assert_link_mode(mode: str, src: Path, dest: Path) -> None:
    assert mode in {"symlink", "hardlink", "copy"}
    if mode == "symlink":
        assert dest.is_symlink()
    else:
        assert not dest.is_symlink()

    same = os.path.samefile(src, dest)
    if mode == "copy":
        assert not same
    else:
        assert same


def test_materialize_workspace_snapshot_records_link_mode(tmp_path: Path) -> None:
    workspaces = tmp_path / "workspaces"
    run_dir = workspaces / "run-1"
    run_dir.mkdir(parents=True, exist_ok=True)

    _write_text(run_dir / "report_summary.json", json.dumps({"run_id": "run-1"}))
    _write_text(run_dir / "decision_records.jsonl", '{"seq":0}\n')

    snapshots_dir = tmp_path / "snapshots"
    manifest_path = materialize_workspace_snapshot(run_dir, snapshots_dir)
    assert manifest_path.exists()

    snapshot_run_dir = snapshots_dir / "run-1"
    report_path = snapshot_run_dir / "report_summary.json"
    assert report_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = {entry["path"]: entry for entry in manifest["entries"]}
    assert "run-1/report_summary.json" in entries

    entry = entries["run-1/report_summary.json"]
    mode = entry.get("link_mode")
    assert isinstance(mode, str)
    _assert_link_mode(mode, run_dir / "report_summary.json", report_path)


def test_workspace_snapshot_fallback_deterministic(monkeypatch, tmp_path: Path) -> None:
    workspaces = tmp_path / "workspaces"
    run_dir = workspaces / "run-2"
    run_dir.mkdir(parents=True, exist_ok=True)

    _write_text(run_dir / "report_summary.json", json.dumps({"run_id": "run-2"}))
    _write_text(run_dir / "decision_records.jsonl", '{"seq":0}\n')

    def _raise_symlink(*_args, **_kwargs):
        raise OSError("symlink not permitted")

    from audit import workspace_snapshot as snapshot_mod

    monkeypatch.setattr(snapshot_mod.os, "symlink", _raise_symlink)

    manifest_a = json.loads(
        materialize_workspace_snapshot(run_dir, tmp_path / "snapshots-a").read_text(
            encoding="utf-8"
        )
    )
    manifest_b = json.loads(
        materialize_workspace_snapshot(run_dir, tmp_path / "snapshots-b").read_text(
            encoding="utf-8"
        )
    )

    entries_a = manifest_a["entries"]
    entries_b = manifest_b["entries"]
    assert entries_a == entries_b
    assert "symlink" not in {entry.get("link_mode") for entry in entries_a}

"""Tests for manual/system mode separation."""

import json
import os
from pathlib import Path

import pytest

from manual.run_manual import main as manual_main
from utils.path_guard import guard_manual_write, guard_system_write


pytestmark = pytest.mark.unit


def test_manual_creates_only_workspace_files(tmp_path, monkeypatch):
    repo_root = tmp_path
    monkeypatch.setenv("BUFF_REPO_ROOT", str(repo_root))
    monkeypatch.chdir(repo_root)

    monkeypatch.setattr(
        "sys.argv",
        ["run_manual", "--workspace", "demo", "--symbol", "BTCUSDT", "--timeframe", "1h"],
    )
    manual_main()

    session_path = repo_root / "workspaces" / "demo" / "session.json"
    assert session_path.exists()

    for forbidden in ["features", "reports", "logs"]:
        assert not (repo_root / forbidden).exists()

    payload = json.loads(session_path.read_text(encoding="utf-8"))
    assert payload["workspace"] == "demo"


def test_manual_guard_blocks_reports_path(tmp_path, monkeypatch):
    monkeypatch.setenv("BUFF_REPO_ROOT", str(tmp_path))
    with pytest.raises(PermissionError):
        guard_manual_write(tmp_path / "reports" / "data.json")


def test_system_guard_blocks_workspaces(tmp_path, monkeypatch):
    monkeypatch.setenv("BUFF_REPO_ROOT", str(tmp_path))
    with pytest.raises(PermissionError):
        guard_system_write(tmp_path / "workspaces" / "session.json")


def test_system_cannot_write_to_workspaces(tmp_path, monkeypatch):
    monkeypatch.setenv("BUFF_REPO_ROOT", str(tmp_path))
    with pytest.raises(PermissionError, match="System mode write forbidden"):
        guard_system_write(tmp_path / "workspaces" / "notes.txt")

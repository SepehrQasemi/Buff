"""Path guard tests for risk report writing."""

import json
import os
from pathlib import Path

import pytest

from risk.report import report_path, write_risk_report


pytestmark = pytest.mark.unit


def _base_report(workspace: str | None = None, run_id: str | None = None) -> dict:
    return {
        "run_id": run_id,
        "workspace": workspace,
        "risk_state": "GREEN",
        "permission": "ALLOW",
        "recommended_scale": 1.0,
        "reasons": [],
        "metrics": {"atr_pct": 0.0, "realized_vol": 0.0, "missing_fraction": 0.0, "thresholds": {}},
        "thresholds": {},
        "evaluated_at": "2023-01-01T00:00:00+00:00",
        "risk_report_version": 1,
    }


def test_manual_path_traversal_blocked(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUFF_REPO_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    report = _base_report(workspace="../..")
    with pytest.raises(ValueError, match="path_guard_violation"):
        report_path(report, mode="manual")


def test_system_absolute_path_blocked(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUFF_REPO_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    absolute = str(Path("/tmp/evil")) if os.name != "nt" else "C:\\evil"
    report = _base_report(run_id=absolute)
    with pytest.raises(ValueError, match="path_guard_violation"):
        report_path(report, mode="system")


def test_system_parent_traversal_blocked(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUFF_REPO_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    report = _base_report(run_id="..")
    with pytest.raises(ValueError, match="path_guard_violation"):
        report_path(report, mode="system")


def test_manual_write_valid_json(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUFF_REPO_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    report = _base_report(workspace="demo")
    path = write_risk_report(report, mode="manual")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    assert payload["risk_report_version"] == 1


def test_symlink_escape_blocked(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUFF_REPO_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    workspace_dir = tmp_path / "workspaces" / "linked"
    target_dir = tmp_path / "outside"
    target_dir.mkdir(parents=True, exist_ok=True)
    workspace_dir.parent.mkdir(parents=True, exist_ok=True)
    workspace_dir.mkdir(parents=True, exist_ok=True)

    original_is_symlink = Path.is_symlink

    workspace_dir_resolved = workspace_dir.resolve()

    def _patched_is_symlink(self: Path) -> bool:
        if self.resolve() == workspace_dir_resolved:
            return True
        return original_is_symlink(self)

    monkeypatch.setattr(Path, "is_symlink", _patched_is_symlink)

    report = _base_report(workspace="linked")
    with pytest.raises(ValueError, match="path_guard_violation"):
        report_path(report, mode="manual")

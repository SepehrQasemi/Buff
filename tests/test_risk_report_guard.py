"""Tests for risk report path guarding."""

from pathlib import Path

import pytest

from risk.report import report_path


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


def test_manual_report_path_is_under_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("BUFF_REPO_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    report = _base_report(workspace="demo")
    path = report_path(report, mode="manual")
    expected_base = tmp_path / "workspaces" / "demo" / "reports"
    assert Path(path).resolve().is_relative_to(expected_base.resolve())


def test_manual_report_path_traversal_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("BUFF_REPO_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    report = _base_report(workspace="../..")
    with pytest.raises(ValueError, match="path_guard_violation"):
        report_path(report, mode="manual")


def test_system_report_path_traversal_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("BUFF_REPO_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    report = _base_report(workspace=None, run_id="../evil")
    with pytest.raises(ValueError, match="path_guard_violation"):
        report_path(report, mode="system")


def test_system_report_path_is_under_reports(tmp_path, monkeypatch):
    monkeypatch.setenv("BUFF_REPO_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    report = _base_report()
    path = report_path(report, mode="system")
    expected_base = tmp_path / "reports"
    assert Path(path).resolve().is_relative_to(expected_base.resolve())

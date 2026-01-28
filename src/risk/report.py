"""Risk report writer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from utils.path_guard import guard_manual_write, guard_system_write


def _is_safe_component(value: str) -> bool:
    candidate = Path(value)
    if candidate.is_absolute():
        return False
    parts = candidate.parts
    if len(parts) != 1:
        return False
    if parts[0] in {"", ".", ".."}:
        return False
    if ".." in parts:
        return False
    return True


def _ensure_under_base(target: Path, base: Path) -> None:
    target_resolved = target.resolve()
    base_resolved = base.resolve()
    try:
        target_resolved.relative_to(base_resolved)
    except ValueError as exc:
        raise ValueError("path_guard_violation") from exc


def _report_filename(report: dict[str, Any]) -> str:
    run_id = report.get("run_id")
    if run_id:
        if not _is_safe_component(str(run_id)):
            raise ValueError("path_guard_violation")
        return f"risk_report_{run_id}.json"
    return "risk_report.json"


def report_path(report: dict[str, Any], mode: Literal["manual", "system"]) -> Path:
    filename = _report_filename(report)
    if mode == "manual":
        workspace = report.get("workspace")
        if not workspace:
            raise ValueError("workspace is required for manual risk reports")
        if not _is_safe_component(str(workspace)):
            raise ValueError("path_guard_violation")
        base = Path("workspaces") / workspace / "reports"
        path = base / filename
        _ensure_under_base(path, base)
        return guard_manual_write(path)

    if mode == "system":
        base = Path("reports")
        path = base / filename
        _ensure_under_base(path, base)
        return guard_system_write(path)

    raise ValueError(f"Unknown mode: {mode}")


def write_risk_report(report: dict[str, Any], mode: Literal["manual", "system"]) -> Path:
    path = report_path(report, mode)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, sort_keys=True)
    path.write_text(payload + "\n", encoding="utf-8")
    return path

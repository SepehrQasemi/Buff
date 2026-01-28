"""Risk report writer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from utils.path_guard import guard_manual_write, guard_system_write


def _report_filename(report: dict[str, Any]) -> str:
    run_id = report.get("run_id")
    if run_id:
        return f"risk_report_{run_id}.json"
    return "risk_report.json"


def report_path(report: dict[str, Any], mode: Literal["manual", "system"]) -> Path:
    filename = _report_filename(report)
    if mode == "manual":
        workspace = report.get("workspace")
        if not workspace:
            raise ValueError("workspace is required for manual risk reports")
        path = Path("workspaces") / workspace / "reports" / filename
        return guard_manual_write(path)

    if mode == "system":
        path = Path("reports") / filename
        return guard_system_write(path)

    raise ValueError(f"Unknown mode: {mode}")


def write_risk_report(report: dict[str, Any], mode: Literal["manual", "system"]) -> Path:
    path = report_path(report, mode)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, sort_keys=True)
    path.write_text(payload + "\n", encoding="utf-8")
    return path

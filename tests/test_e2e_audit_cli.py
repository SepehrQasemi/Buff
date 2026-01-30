from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests.fixtures.workspace_factory import make_workspace


def _run_cli(args: list[str], workspaces: Path) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "src.cli", "--workspaces", str(workspaces)] + args
    return subprocess.run(cmd, capture_output=True, text=True)


def test_e2e_audit_cli(tmp_path: Path) -> None:
    workspaces = make_workspace(
        tmp_path,
        {"run_ok": "ok", "run_invalid": "invalid", "run_empty": "empty"},
    )

    result_index = _run_cli(["index"], workspaces)
    assert result_index.returncode == 0

    index_json = workspaces / "index.json"
    index_md = workspaces / "index.md"
    assert index_json.exists()
    assert index_md.exists()
    md_text = index_md.read_text(encoding="utf-8")
    assert "None" not in md_text
    assert "run_invalid" in md_text
    assert "invalid" in md_text

    result_report = _run_cli(["report", "--run-id", "run_ok"], workspaces)
    assert result_report.returncode == 0
    assert (workspaces / "run_ok" / "report.md").exists()
    assert (workspaces / "run_ok" / "report_summary.json").exists()

    result_validate_ok = _run_cli(["validate-run", "--run-id", "run_ok"], workspaces)
    assert result_validate_ok.returncode == 0

    result_validate_bad = _run_cli(["validate-run", "--run-id", "run_invalid"], workspaces)
    assert result_validate_bad.returncode != 0
    assert result_validate_bad.stderr.startswith("ERROR:")

    first_json = index_json.read_bytes()
    first_md = index_md.read_bytes()
    result_index_repeat = _run_cli(["index"], workspaces)
    assert result_index_repeat.returncode == 0
    assert index_json.read_bytes() == first_json
    assert index_md.read_bytes() == first_md

    report_path = workspaces / "run_ok" / "report.md"
    first_report = report_path.read_bytes()
    result_report_repeat = _run_cli(["report", "--run-id", "run_ok"], workspaces)
    assert result_report_repeat.returncode == 0
    assert report_path.read_bytes() == first_report

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _run_export(
    *,
    run_id: str,
    runs_root: Path,
    out_path: Path,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        str(_repo_root() / "scripts" / "export_report.py"),
        "--run-id",
        run_id,
        "--runs-root",
        str(runs_root),
        "--out",
        str(out_path),
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


def test_export_report_from_golden(tmp_path: Path) -> None:
    runs_root = _repo_root() / "tests" / "goldens" / "phase6"
    run_id = "hold_sample"
    out_path = tmp_path / "report.md"

    result = _run_export(run_id=run_id, runs_root=runs_root, out_path=out_path)

    assert result.returncode == 0, result.stderr
    assert out_path.exists()

    manifest = json.loads((runs_root / run_id / "manifest.json").read_text(encoding="utf-8"))
    metrics = json.loads((runs_root / run_id / "metrics.json").read_text(encoding="utf-8"))

    report = out_path.read_text(encoding="utf-8")
    assert f"Run ID: {run_id}" in report
    assert f"Inputs Hash: {manifest.get('inputs_hash')}" in report
    assert f"- num_trades: {metrics.get('num_trades')}" in report


def test_export_report_missing_metrics(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_id = "missing_metrics"
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True)

    fixture_manifest = (
        _repo_root() / "tests" / "goldens" / "phase6" / "hold_sample" / "manifest.json"
    )
    (run_dir / "manifest.json").write_text(
        fixture_manifest.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    out_path = tmp_path / "report.md"
    result = _run_export(run_id=run_id, runs_root=runs_root, out_path=out_path)

    assert result.returncode != 0
    payload = json.loads(result.stderr.strip())
    assert payload["code"] == "metrics_missing"
    assert payload["error"]["code"] == "metrics_missing"
    assert not out_path.exists()

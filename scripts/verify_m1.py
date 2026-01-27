"""Verification and smoke-test workflow for M1."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> None:
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print("FAIL: " + " ".join(cmd))
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)
        raise SystemExit(result.returncode)


def _compare_reports(path1: Path, path2: Path) -> None:
    text1 = path1.read_text(encoding="utf-8")
    text2 = path2.read_text(encoding="utf-8")
    if text1 != text2:
        print("FAIL: report outputs are not identical")
        raise SystemExit(1)

    obj1 = json.loads(text1)
    obj2 = json.loads(text2)
    if obj1 != obj2:
        print("FAIL: report JSON content differs")
        raise SystemExit(1)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    tmp_dir = repo_root / ".tmp_verify_m1"

    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)

    data_dir = tmp_dir / "data" / "clean"
    reports_dir = tmp_dir / "reports"

    symbols = "BTCUSDT,ETHUSDT"
    timeframe = "1h"

    success = False
    try:
        _run(
            [
                sys.executable,
                "-m",
                "src.data.run_ingest",
                "--offline",
                "--fixtures_dir",
                str(repo_root / "tests" / "fixtures" / "ohlcv"),
                "--symbols",
                symbols,
                "--timeframe",
                timeframe,
                "--data_dir",
                str(data_dir),
                "--reports_dir",
                str(reports_dir),
            ],
            cwd=repo_root,
        )

        _run(
            [
                sys.executable,
                "-m",
                "src.data.validate",
                "--symbols",
                symbols,
                "--timeframe",
                timeframe,
                "--data_dir",
                str(data_dir),
            ],
            cwd=repo_root,
        )

        report1 = reports_dir / "data_quality_1.json"
        report2 = reports_dir / "data_quality_2.json"

        _run(
            [
                sys.executable,
                "-m",
                "src.data.report",
                "--symbols",
                symbols,
                "--timeframe",
                timeframe,
                "--data_dir",
                str(data_dir),
                "--out",
                str(report1),
            ],
            cwd=repo_root,
        )

        _run(
            [
                sys.executable,
                "-m",
                "src.data.report",
                "--symbols",
                symbols,
                "--timeframe",
                timeframe,
                "--data_dir",
                str(data_dir),
                "--out",
                str(report2),
            ],
            cwd=repo_root,
        )

        _compare_reports(report1, report2)

        verify_env = dict(**__import__("os").environ)
        verify_env["PYTHONPATH"] = str(repo_root)

        _run(
            [
                sys.executable,
                "-m",
                "src.data.verify_outputs",
            ],
            cwd=tmp_dir,
            env=verify_env,
        )

        _run(
            [
                sys.executable,
                "-m",
                "src.knowledge.parser",
                "--path",
                str(repo_root / "knowledge" / "technical_rules.yaml"),
            ],
            cwd=repo_root,
        )

        _run([sys.executable, "-m", "pytest", "-q"], cwd=repo_root)

        print("PASS: M1 verification workflow complete")
        success = True
    finally:
        if success and tmp_dir.exists():
            shutil.rmtree(tmp_dir)


if __name__ == "__main__":
    main()

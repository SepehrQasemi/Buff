from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_cli_replay_exit_codes(tmp_path: Path) -> None:
    decision_input = Path("tests/fixtures/decision_payload.json")
    snapshot_input = Path("tests/fixtures/snapshot_payload.json")

    decisions_dir = tmp_path / "decisions"
    snapshots_dir = tmp_path / "snapshots"

    record_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.audit.record_decision",
            "--input",
            str(decision_input),
            "--out",
            str(decisions_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert record_proc.returncode == 0

    decision_path = decisions_dir / "2026-02-01" / "decision_dec-001.json"
    assert decision_path.exists()

    snapshot_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.audit.make_snapshot",
            "--input",
            str(snapshot_input),
            "--out",
            str(snapshots_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert snapshot_proc.returncode == 0

    snapshot_path = Path(snapshot_proc.stdout.strip())
    assert snapshot_path.exists()

    replay_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.audit.replay",
            "--decision",
            str(decision_path),
            "--snapshot",
            str(snapshot_path),
            "--strict",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert replay_proc.returncode == 0
    assert "REPLAY_OK strict-core" in replay_proc.stdout


def test_cli_replay_out_is_directory(tmp_path: Path) -> None:
    decision_input = Path("tests/fixtures/decision_payload.json")
    snapshot_input = Path("tests/fixtures/snapshot_payload.json")

    decisions_dir = tmp_path / "decisions"
    snapshots_dir = tmp_path / "snapshots"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "src.audit.record_decision",
            "--input",
            str(decision_input),
            "--out",
            str(decisions_dir),
        ],
        check=True,
    )
    decision_path = decisions_dir / "2026-02-01" / "decision_dec-001.json"

    snapshot_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.audit.make_snapshot",
            "--input",
            str(snapshot_input),
            "--out",
            str(snapshots_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert snapshot_proc.returncode == 0
    snapshot_path = Path(snapshot_proc.stdout.strip())
    assert snapshot_path.exists()

    out_dir = tmp_path / "replay_out"
    replay_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.audit.replay",
            "--decision",
            str(decision_path),
            "--snapshot",
            str(snapshot_path),
            "--strict",
            "--out",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert replay_proc.returncode == 0
    assert (out_dir / "replay_dec-001.json").exists()


def test_cli_replay_out_file_path_fails(tmp_path: Path) -> None:
    decision_input = Path("tests/fixtures/decision_payload.json")
    snapshot_input = Path("tests/fixtures/snapshot_payload.json")

    decisions_dir = tmp_path / "decisions"
    snapshots_dir = tmp_path / "snapshots"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "src.audit.record_decision",
            "--input",
            str(decision_input),
            "--out",
            str(decisions_dir),
        ],
        check=True,
    )
    decision_path = decisions_dir / "2026-02-01" / "decision_dec-001.json"

    snapshot_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.audit.make_snapshot",
            "--input",
            str(snapshot_input),
            "--out",
            str(snapshots_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert snapshot_proc.returncode == 0
    snapshot_path = Path(snapshot_proc.stdout.strip())
    assert snapshot_path.exists()

    out_path = tmp_path / "replay_output.json"
    replay_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.audit.replay",
            "--decision",
            str(decision_path),
            "--snapshot",
            str(snapshot_path),
            "--strict",
            "--out",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert replay_proc.returncode == 2
    assert "ERROR: --out must be a directory" in replay_proc.stderr


def test_cli_replay_writes_diff_json(tmp_path: Path) -> None:
    decision_input = Path("tests/fixtures/decision_payload.json")
    decisions_dir = tmp_path / "decisions"
    snapshots_dir = tmp_path / "snapshots"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "src.audit.record_decision",
            "--input",
            str(decision_input),
            "--out",
            str(decisions_dir),
        ],
        check=True,
    )
    decision_path = decisions_dir / "2026-02-01" / "decision_dec-001.json"

    snapshot_payload = json.loads(Path("tests/fixtures/snapshot_payload.json").read_text())
    snapshot_payload["features"] = {
        "trend_state": "flat",
        "volatility_regime": "mid",
        "structure_state": "meanrevert",
    }
    snapshot_path = snapshots_dir / "snapshot_modified.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(snapshot_payload), encoding="utf-8")

    diff_path = tmp_path / "diff.json"
    replay_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.audit.replay",
            "--decision",
            str(decision_path),
            "--snapshot",
            str(snapshot_path),
            "--strict",
            "--json",
            str(diff_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert replay_proc.returncode == 2
    assert "REPLAY_MISMATCH" in replay_proc.stdout
    assert diff_path.exists()

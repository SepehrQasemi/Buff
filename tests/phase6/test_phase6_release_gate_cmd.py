from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_phase6_release_gate_command() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    cmd = [sys.executable, "scripts/phase6_release_gate.py"]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_root)
    assert result.returncode == 0, result.stderr
    assert "phase6_release_gate: OK" in result.stdout

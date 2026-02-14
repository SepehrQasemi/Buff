from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_release_gate_runs_without_pythonpath(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["BUFF_RELEASE_GATE_TMP"] = str(tmp_path)

    result = subprocess.run(
        [sys.executable, "src/tools/phase6_release_gate.py"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "phase6_release_gate: OK" in result.stdout

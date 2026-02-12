from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_self_check_script_runs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    src_path = repo_root / "src"
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(src_path) + (os.pathsep + existing if existing else "")
    proc = subprocess.run(
        [sys.executable, "-m", "src.audit.self_check"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert proc.returncode == 0
    assert "SELF_CHECK strict-core OK" in proc.stdout
    assert "SELF_CHECK strict-full OK" in proc.stdout

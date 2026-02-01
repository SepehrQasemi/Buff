from __future__ import annotations

import subprocess
import sys


def test_self_check_script_runs() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "src.audit.self_check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "SELF_CHECK strict-core OK" in proc.stdout
    assert "SELF_CHECK strict-full OK" in proc.stdout

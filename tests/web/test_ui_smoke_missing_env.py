from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


def test_ui_smoke_missing_env_message() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")

    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    for key in ("API_BASE_URL", "UI_BASE_URL", "API_BASE", "UI_BASE", "NEXT_PUBLIC_API_BASE"):
        env.pop(key, None)

    result = subprocess.run(
        [node, "apps/web/scripts/ui-smoke.mjs"],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    stderr = result.stderr
    assert "API_BASE_URL" in stderr
    assert "UI_BASE_URL" in stderr
    assert "verify_phase1.py --with-services --real-smoke" in stderr
    assert "$env:API_BASE_URL" in stderr
    assert "export API_BASE_URL" in stderr

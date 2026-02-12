from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    cmd = [sys.executable, "-m", "src.tools.phase6_release_gate"]
    env = os.environ.copy()
    src_path = repo_root / "src"
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(src_path) + (os.pathsep + existing if existing else "")
    result = subprocess.run(cmd, cwd=repo_root, env=env)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()

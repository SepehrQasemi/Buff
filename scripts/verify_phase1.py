from __future__ import annotations

import subprocess
import sys
from pathlib import Path


STEPS = [
    ("ruff check", ["ruff", "check", "."]),
    ("ruff format", ["ruff", "format", "--check", "."]),
    ("pytest", ["pytest", "-q"]),
    ("ui smoke", ["node", "apps/web/scripts/ui-smoke.mjs"]),
]


def run_step(label: str, cmd: list[str], cwd: Path) -> int:
    print(f"\n==> {label}")
    result = subprocess.run(cmd, cwd=str(cwd))
    if result.returncode != 0:
        print(f"!! {label} failed (exit {result.returncode})")
    else:
        print(f"OK {label}")
    return result.returncode


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    for label, cmd in STEPS:
        code = run_step(label, cmd, repo_root)
        if code != 0:
            return code
    print("\nPhase-1 verification complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import re
from pathlib import Path

FORBIDDEN_IMPORT = re.compile(
    r"^\s*(?:from|import)\s+(?:requests|httpx|aiohttp|websocket|websockets|socket)\b"
)
FORBIDDEN_LIVE_EXEC = re.compile(r"^\s*(?:from|import)\s+execution\.brokers\b")


def test_runtime_surface_has_no_network_imports() -> None:
    targets: list[Path] = [Path("apps/api/main.py"), Path("apps/api/artifacts.py")]
    targets.extend(sorted(Path("apps/api/phase6").glob("*.py")))

    violations: list[str] = []
    for path in targets:
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if FORBIDDEN_IMPORT.search(line):
                violations.append(f"{path}:{line_no}:{line.strip()}")
            if FORBIDDEN_LIVE_EXEC.search(line):
                violations.append(f"{path}:{line_no}:{line.strip()}")

    assert not violations, "\n".join(violations)

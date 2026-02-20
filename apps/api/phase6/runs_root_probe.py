from __future__ import annotations

import uuid
from pathlib import Path


def check_runs_root_writable(runs_root: Path) -> tuple[bool, str | None]:
    probe = runs_root / f".buff_write_check_{uuid.uuid4().hex}"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return False, str(exc)
    return True, None

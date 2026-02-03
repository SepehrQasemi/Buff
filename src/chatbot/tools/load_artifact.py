from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _ensure_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"missing_artifact:{path}")
    if not path.is_file():
        raise FileNotFoundError(f"missing_artifact:{path}")


def load_text(path: Path) -> str:
    _ensure_file(path)
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> Any:
    _ensure_file(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid_json:{path}") from exc

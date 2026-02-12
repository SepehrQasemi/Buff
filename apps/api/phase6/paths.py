from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

RUNS_ROOT_ENV = "RUNS_ROOT"


def get_runs_root() -> Path | None:
    value = os.environ.get(RUNS_ROOT_ENV)
    if not value:
        return None
    return Path(value).expanduser().resolve()


def ensure_runs_root() -> Path:
    root = get_runs_root()
    if root is None:
        raise RuntimeError("RUNS_ROOT_UNSET")
    root.mkdir(parents=True, exist_ok=True)
    return root


def is_within_root(candidate: Path, root: Path) -> bool:
    try:
        return candidate.is_relative_to(root)
    except AttributeError:
        return candidate == root or root in candidate.parents


def resolve_run_dir_any(run_id: str, roots: Iterable[Path]) -> Path | None:
    for root in roots:
        candidate = (root / run_id).resolve()
        if not is_within_root(candidate, root):
            continue
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None

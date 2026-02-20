from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable

from ..security.user_context import is_valid_user_id

RUNS_ROOT_ENV = "RUNS_ROOT"
_COMPONENT_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


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


def _normalize_component(value: str) -> str:
    return (value or "").strip()


def is_valid_component(value: str) -> bool:
    normalized = _normalize_component(value)
    if normalized in {"", ".", ".."}:
        return False
    return bool(_COMPONENT_PATTERN.match(normalized))


def validate_user_id(user_id: str) -> str:
    normalized = _normalize_component(user_id)
    if not is_valid_user_id(normalized):
        raise ValueError("USER_INVALID")
    return normalized


def validate_run_id(run_id: str) -> str:
    normalized = _normalize_component(run_id)
    if not is_valid_component(normalized):
        raise ValueError("RUN_ID_INVALID")
    return normalized


def is_within_root(candidate: Path, root: Path) -> bool:
    try:
        return candidate.is_relative_to(root)
    except AttributeError:
        return candidate == root or root in candidate.parents


def users_root(base_runs_root: Path) -> Path:
    return base_runs_root / "users"


def user_root(base_runs_root: Path, user_id: str) -> Path:
    normalized_user = validate_user_id(user_id)
    return users_root(base_runs_root) / normalized_user


def user_runs_root(base_runs_root: Path, user_id: str) -> Path:
    return user_root(base_runs_root, user_id) / "runs"


def user_uploads_root(base_runs_root: Path, user_id: str) -> Path:
    return user_root(base_runs_root, user_id) / "inputs"


def user_imports_root(base_runs_root: Path, user_id: str) -> Path:
    return user_root(base_runs_root, user_id) / "imports"


def run_dir(base_runs_root: Path, user_id: str, run_id: str) -> Path:
    normalized_run = validate_run_id(run_id)
    return user_runs_root(base_runs_root, user_id) / normalized_run


def user_registry_path(base_runs_root: Path, user_id: str) -> Path:
    return user_root(base_runs_root, user_id) / "index.json"


def resolve_run_dir_any(run_id: str, roots: Iterable[Path]) -> Path | None:
    if not is_valid_component(run_id):
        return None
    for root in roots:
        candidate = (root / run_id).resolve()
        if not is_within_root(candidate, root):
            continue
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None

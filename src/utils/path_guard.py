"""Path guard for manual vs system mode separation."""

from __future__ import annotations

import os
from pathlib import Path


def _repo_root() -> Path:
    override = os.environ.get("BUFF_REPO_ROOT")
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parents[3]


def _ensure_under_root(target: Path, root: Path, label: str) -> None:
    target_resolved = target.resolve()
    root_resolved = root.resolve()
    try:
        target_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise PermissionError(
            f"{label} write forbidden outside {root_resolved}: {target_resolved}"
        ) from exc


def guard_manual_write(path: str | Path) -> Path:
    """Allow only workspaces/ writes for manual mode."""
    root = _repo_root() / "workspaces"
    target = Path(path)
    if not target.is_absolute():
        target = _repo_root() / target
    _ensure_under_root(target, root, "Manual mode")
    return target


def guard_system_write(path: str | Path) -> Path:
    """Allow only features/, reports/, logs/ writes for system mode."""
    repo = _repo_root()
    target = Path(path)
    if not target.is_absolute():
        target = repo / target

    allowed = [repo / "features", repo / "reports", repo / "logs"]
    for root in allowed:
        try:
            target.resolve().relative_to(root.resolve())
            return target
        except ValueError:
            continue

    raise PermissionError(
        f"System mode write forbidden outside features/, reports/, logs/: {target.resolve()}"
    )

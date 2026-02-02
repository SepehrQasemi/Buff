from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil


_MANIFEST_NAME = "snapshot_manifest.json"
_MANIFEST_VERSION = 1
_ALLOWED_FILENAMES = {
    "decision_records.jsonl",
    "report_summary.json",
    "report.md",
    "ohlcv_1m.parquet",
    "data_quality.json",
}
_ALLOWED_JSONL_PREFIX = "decision_records_"


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    size_bytes: int
    sha256: str


class WorkspaceSnapshotError(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


_LINK_MODES = {"symlink", "hardlink", "copy"}


def _utc_now_z() -> str:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return ts.replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _link_file(src: Path, dest: Path) -> str:
    if dest.exists():
        raise WorkspaceSnapshotError("snapshot_target_exists")
    try:
        os.symlink(src, dest)
        return "symlink"
    except (OSError, NotImplementedError):
        try:
            os.link(src, dest)
            return "hardlink"
        except (OSError, NotImplementedError):
            shutil.copy2(src, dest)
            return "copy"


def _is_included(name: str) -> bool:
    if name in _ALLOWED_FILENAMES:
        return True
    if name.startswith(_ALLOWED_JSONL_PREFIX) and name.endswith(".jsonl"):
        return True
    return False


def _iter_workspace_files(run_dir: Path) -> list[Path]:
    if not run_dir.exists():
        return []
    files = [path for path in run_dir.iterdir() if path.is_file() and _is_included(path.name)]
    return sorted(files, key=lambda path: path.name)


def _entries_from_files(run_dir: Path, workspace_dir: Path) -> list[ManifestEntry]:
    entries: list[ManifestEntry] = []
    for file_path in _iter_workspace_files(run_dir):
        rel = file_path.relative_to(workspace_dir).as_posix()
        size = file_path.stat().st_size
        entries.append(
            ManifestEntry(
                path=rel,
                size_bytes=int(size),
                sha256=_sha256_file(file_path),
            )
        )
    return sorted(entries, key=lambda entry: entry.path)


def create_workspace_manifest(run_dir: Path, *, link_modes: dict[str, str] | None = None) -> Path:
    run_dir = run_dir.resolve()
    workspace_dir = run_dir.parent
    run_id = run_dir.name

    entries = _entries_from_files(run_dir, workspace_dir)
    entries_payload: list[dict[str, object]] = []
    for entry in entries:
        record: dict[str, object] = {
            "path": entry.path,
            "size_bytes": entry.size_bytes,
            "sha256": entry.sha256,
        }
        if link_modes is not None:
            mode = link_modes.get(entry.path)
            if mode not in _LINK_MODES:
                raise WorkspaceSnapshotError("invalid_link_mode")
            record["link_mode"] = mode
        entries_payload.append(record)

    payload = {
        "run_id": run_id,
        "created_at": _utc_now_z(),
        "snapshot_version": _MANIFEST_VERSION,
        "entries": entries_payload,
    }

    manifest_path = run_dir / _MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def materialize_workspace_snapshot(run_dir: Path, out_dir: Path) -> Path:
    run_dir = run_dir.resolve()
    out_dir = out_dir.resolve()
    if not run_dir.exists():
        raise WorkspaceSnapshotError("run_dir_missing")

    snapshot_run_dir = out_dir / run_dir.name
    if snapshot_run_dir.exists():
        raise WorkspaceSnapshotError("snapshot_exists")
    snapshot_run_dir.mkdir(parents=True, exist_ok=False)

    link_modes: dict[str, str] = {}
    for file_path in _iter_workspace_files(run_dir):
        target = snapshot_run_dir / file_path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = _link_file(file_path, target)
        rel = target.relative_to(out_dir).as_posix()
        link_modes[rel] = mode

    return create_workspace_manifest(snapshot_run_dir, link_modes=link_modes)


def verify_workspace_manifest(manifest_path: Path) -> None:
    manifest_path = manifest_path.resolve()
    run_dir = manifest_path.parent
    workspace_dir = run_dir.parent

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise WorkspaceSnapshotError("invalid_manifest_json")

    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise WorkspaceSnapshotError("workspace_mismatch")
    if run_id != run_dir.name:
        raise WorkspaceSnapshotError("workspace_mismatch")

    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise WorkspaceSnapshotError("invalid_manifest_entries")

    expected_paths: list[str] = []
    for entry in entries:
        path = entry.get("path")
        size = entry.get("size_bytes")
        sha = entry.get("sha256")
        if not isinstance(path, str) or not isinstance(size, int) or not isinstance(sha, str):
            raise WorkspaceSnapshotError("invalid_manifest_entries")
        if not path.startswith(f"{run_id}/"):
            raise WorkspaceSnapshotError("workspace_mismatch")
        expected_paths.append(path)

        file_path = workspace_dir / Path(path)
        if not file_path.exists():
            raise WorkspaceSnapshotError("missing_file")
        actual_size = file_path.stat().st_size
        if actual_size != size:
            raise WorkspaceSnapshotError("hash_mismatch")
        actual_sha = _sha256_file(file_path)
        if actual_sha != sha:
            raise WorkspaceSnapshotError("hash_mismatch")

    current_paths = [
        path.relative_to(workspace_dir).as_posix() for path in _iter_workspace_files(run_dir)
    ]
    extra_paths = sorted(set(current_paths) - set(expected_paths))
    if extra_paths:
        raise WorkspaceSnapshotError("extra_file")

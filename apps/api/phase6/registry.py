from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

from .canonical import write_canonical_json
from .paths import is_within_root

REGISTRY_FILENAME = "index.json"
REGISTRY_SCHEMA_VERSION = "1.0.0"
REGISTRY_LOCK_FILENAME = ".registry.lock"
REGISTRY_LOCK_TIMEOUT_SECONDS = 2.0

REQUIRED_ARTIFACTS = (
    "manifest.json",
    "config.json",
    "metrics.json",
    "equity_curve.json",
    "trades.jsonl",
    "timeline.json",
    "decision_records.jsonl",
)


@dataclass
class RegistryLock:
    path: Path
    timeout_seconds: float = REGISTRY_LOCK_TIMEOUT_SECONDS
    _handle: Any | None = None
    _locked: bool = False

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a+", encoding="utf-8")
        start = time.monotonic()
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._locked = True
                return True
            except OSError:
                if time.monotonic() - start >= self.timeout_seconds:
                    return False
                time.sleep(0.05)

    def release(self) -> None:
        if not self._handle or not self._locked:
            return
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._locked = False
            self._handle.close()
            self._handle = None

    def __enter__(self) -> "RegistryLock":
        if not self.acquire():
            raise TimeoutError("REGISTRY_LOCK_TIMEOUT")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _registry_path(runs_root: Path) -> Path:
    return runs_root / REGISTRY_FILENAME


def _load_registry_payload(runs_root: Path) -> dict[str, Any]:
    path = _registry_path(runs_root)
    if not path.exists():
        return {"schema_version": REGISTRY_SCHEMA_VERSION, "generated_at": None, "runs": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"schema_version": REGISTRY_SCHEMA_VERSION, "generated_at": None, "runs": []}
    if not isinstance(payload, dict):
        return {"schema_version": REGISTRY_SCHEMA_VERSION, "generated_at": None, "runs": []}
    payload.setdefault("schema_version", REGISTRY_SCHEMA_VERSION)
    payload.setdefault("runs", [])
    if not isinstance(payload.get("runs"), list):
        payload["runs"] = []
    return payload


def _artifact_status(run_dir: Path) -> tuple[str, list[str]]:
    missing = [name for name in REQUIRED_ARTIFACTS if not (run_dir / name).exists()]
    if missing:
        return "CORRUPTED", missing
    return "OK", []


def _manifest_path(run_id: str) -> str:
    return f"{run_id}/manifest.json"


def _artifacts_present(run_dir: Path) -> list[str]:
    items = [child.name for child in run_dir.iterdir() if child.is_file()]
    return sorted(items)


def build_registry_entry(run_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    run_id = str(manifest.get("run_id") or run_dir.name)
    status, missing = _artifact_status(run_dir)
    manifest_status = manifest.get("status")
    if status != "CORRUPTED" and isinstance(manifest_status, str):
        status = manifest_status

    entry = {
        "run_id": run_id,
        "created_at": manifest.get("created_at"),
        "symbol": (manifest.get("data") or {}).get("symbol"),
        "timeframe": (manifest.get("data") or {}).get("timeframe"),
        "status": status,
        "manifest_path": _manifest_path(run_id),
        "artifacts_present": _artifacts_present(run_dir),
        "inputs_hash": manifest.get("inputs_hash"),
        "strategy_id": (manifest.get("strategy") or {}).get("id"),
    }
    if missing:
        entry["missing_artifacts"] = missing
    return entry


def upsert_registry_entry(
    runs_root: Path,
    run_dir: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    registry = _load_registry_payload(runs_root)
    runs = registry.get("runs", [])
    entry = build_registry_entry(run_dir, manifest)
    replaced = False
    for idx, existing in enumerate(runs):
        if isinstance(existing, dict) and existing.get("run_id") == entry["run_id"]:
            runs[idx] = entry
            replaced = True
            break
    if not replaced:
        runs.append(entry)
    registry["runs"] = _sorted_runs(runs)
    if registry.get("generated_at") is None:
        registry["generated_at"] = manifest.get("created_at")
    registry["generated_at"] = registry.get("generated_at") or manifest.get("created_at")
    _write_registry_payload(runs_root, registry)
    return entry


def reconcile_registry(runs_root: Path) -> dict[str, Any]:
    registry = _load_registry_payload(runs_root)
    runs = registry.get("runs", [])
    updated = False
    for idx, entry in enumerate(runs):
        if not isinstance(entry, dict):
            continue
        run_id = entry.get("run_id")
        if not run_id:
            continue
        run_dir = (runs_root / run_id).resolve()
        if not is_within_root(run_dir, runs_root) or not run_dir.exists():
            entry["status"] = "CORRUPTED"
            updated = True
            continue
        status, missing = _artifact_status(run_dir)
        if status == "CORRUPTED" and entry.get("status") != "CORRUPTED":
            entry["status"] = "CORRUPTED"
            entry["missing_artifacts"] = missing
            updated = True
        entry["artifacts_present"] = _artifacts_present(run_dir)
    registry["runs"] = _sorted_runs(runs)
    if updated:
        _write_registry_payload(runs_root, registry)
    return registry


def load_registry(runs_root: Path) -> dict[str, Any]:
    return _load_registry_payload(runs_root)


def get_registry_entry(runs_root: Path, run_id: str) -> dict[str, Any] | None:
    registry = _load_registry_payload(runs_root)
    runs = registry.get("runs", [])
    for entry in runs:
        if isinstance(entry, dict) and entry.get("run_id") == run_id:
            return entry
    return None


def _write_registry_payload(runs_root: Path, payload: dict[str, Any]) -> None:
    path = _registry_path(runs_root)
    tmp_path = path.with_suffix(".tmp")
    write_canonical_json(tmp_path, payload)
    os.replace(tmp_path, path)
    _fsync_dir(runs_root)


def _sorted_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [entry for entry in runs if isinstance(entry, dict)],
        key=lambda item: str(item.get("run_id") or ""),
    )


def compute_inputs_hash(canonical_bytes: bytes) -> str:
    return sha256(canonical_bytes).hexdigest()


def lock_registry(runs_root: Path) -> RegistryLock:
    return RegistryLock(runs_root / REGISTRY_LOCK_FILENAME)

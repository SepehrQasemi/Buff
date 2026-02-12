from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from .discovery import PluginType, discover_plugins
from .validation import validate_all

ValidationStatus = Literal["VALID", "INVALID"]
INDEX_LOCK_FILENAME = ".index.lock"
INDEX_LOCK_TTL_SECONDS = 120


@dataclass(frozen=True)
class ValidationIndex:
    payload: dict[str, Any]


def list_valid_indicators(artifacts_root: Path) -> list[dict[str, Any]]:
    return _list_by_status(artifacts_root, plugin_type="indicator", status="VALID")


def list_valid_strategies(artifacts_root: Path) -> list[dict[str, Any]]:
    return _list_by_status(artifacts_root, plugin_type="strategy", status="VALID")


def list_invalid_indicators(artifacts_root: Path) -> list[dict[str, Any]]:
    return _list_by_status(artifacts_root, plugin_type="indicator", status="INVALID")


def list_invalid_strategies(artifacts_root: Path) -> list[dict[str, Any]]:
    return _list_by_status(artifacts_root, plugin_type="strategy", status="INVALID")


def get_validation_summary(artifacts_root: Path) -> dict[str, Any]:
    index = _load_index_or_rebuild(artifacts_root)
    plugins = index.payload.get("plugins", {})
    invalid_entries = [entry for entry in plugins.values() if entry.get("status") == "INVALID"]
    reason_counts: dict[str, int] = {}
    for entry in invalid_entries:
        details = _load_artifact_details(artifacts_root, entry)
        for code in details.get("reason_codes", []):
            reason_counts[code] = reason_counts.get(code, 0) + 1
    top_codes = sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))
    return {
        "total_plugins": index.payload.get("total_plugins", 0),
        "total_valid": index.payload.get("total_valid", 0),
        "total_invalid": index.payload.get("total_invalid", 0),
        "top_reason_codes": [{"code": code, "count": count} for code, count in top_codes[:5]],
    }


def get_validation_summary_from_artifacts(artifacts_root: Path) -> dict[str, Any]:
    payload, error, total_override = _load_index_for_summary(artifacts_root)
    plugins = payload.get("plugins", {})
    invalid_entries = [entry for entry in plugins.values() if entry.get("status") == "INVALID"]
    reason_counts: dict[str, int] = {}
    for entry in invalid_entries:
        details = _load_artifact_details(artifacts_root, entry)
        for code in details.get("reason_codes", []):
            reason_counts[code] = reason_counts.get(code, 0) + 1
    top_codes = sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))
    total_plugins = payload.get("total_plugins", 0)
    total_valid = payload.get("total_valid", 0)
    total_invalid = payload.get("total_invalid", 0)
    if error:
        total_plugins = total_override if total_override is not None else 0
        total_valid = 0
        total_invalid = total_plugins
    summary: dict[str, Any] = {
        "total": total_plugins,
        "valid": total_valid,
        "invalid": total_invalid,
        "top_reason_codes": [{"code": code, "count": count} for code, count in top_codes[:5]],
        "index_built_at_utc": payload.get("index_built_at"),
        "index_content_hash": payload.get("content_hash", ""),
    }
    if error:
        summary["error"] = error
    return summary


def _list_by_status(
    artifacts_root: Path, plugin_type: PluginType, status: ValidationStatus
) -> list[dict[str, Any]]:
    index = _load_index_or_rebuild(artifacts_root)
    plugins = index.payload.get("plugins", {})
    entries = [
        entry
        for entry in plugins.values()
        if entry.get("plugin_type") == plugin_type and entry.get("status") == status
    ]
    if status == "VALID":
        payload = [_active_payload(entry) for entry in entries]
    else:
        payload = [_failed_payload(artifacts_root, entry) for entry in entries]
    return sorted(payload, key=lambda item: item.get("id") or "")


def _load_index_or_rebuild(artifacts_root: Path) -> ValidationIndex:
    artifacts_root = Path(artifacts_root)
    index_path = artifacts_root / "plugin_validation" / "index.json"
    repo_root = _resolve_repo_root(artifacts_root)

    payload = _read_index(index_path)
    if payload is None:
        payload = _rebuild_index_with_lock(repo_root, artifacts_root)
        return ValidationIndex(payload=payload)

    if _index_stale(payload, repo_root, artifacts_root):
        payload = _rebuild_index_with_lock(repo_root, artifacts_root)
    return ValidationIndex(payload=payload)


def _rebuild_index_with_lock(repo_root: Path, artifacts_root: Path) -> dict[str, Any]:
    with _acquire_index_lock(artifacts_root) as acquired:
        if not acquired:
            return _empty_index()
        return _rebuild_index(repo_root, artifacts_root)


def _load_index_for_summary(
    artifacts_root: Path,
) -> tuple[dict[str, Any], str | None, int | None]:
    artifacts_root = Path(artifacts_root)
    index_path = artifacts_root / "plugin_validation" / "index.json"
    payload = _read_index(index_path)
    if payload is not None:
        return payload, None, None
    if _index_lock_active(artifacts_root):
        total = _count_artifact_files(artifacts_root)
        return _empty_index(), "index rebuild locked", total
    try:
        payload = _rebuild_index_from_artifacts(artifacts_root)
    except Exception as exc:
        total = _count_artifact_files(artifacts_root)
        return _empty_index(), f"summary rebuild failed: {exc}", total
    return payload, None, None


def _rebuild_index(repo_root: Path, artifacts_root: Path) -> dict[str, Any]:
    try:
        candidates = discover_plugins(repo_root)
        validate_all(candidates, artifacts_root / "plugin_validation")
    except Exception:
        return _empty_index()
    payload = _read_index(artifacts_root / "plugin_validation" / "index.json")
    if payload is None:
        return _empty_index()
    return payload


def _rebuild_index_from_artifacts(artifacts_root: Path) -> dict[str, Any]:
    root = artifacts_root / "plugin_validation"
    plugins: dict[str, dict[str, Any]] = {}
    total_valid = 0
    total_invalid = 0
    for plugin_type in ("indicator", "strategy"):
        folder = root / plugin_type
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.json")):
            entry, status = _entry_from_artifact(path, plugin_type)
            key = f"{plugin_type}:{entry.get('id')}"
            plugins[key] = entry
            if status == "VALID":
                total_valid += 1
            else:
                total_invalid += 1
    payload: dict[str, Any] = {
        "index_built_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "total_plugins": len(plugins),
        "total_valid": total_valid,
        "total_invalid": total_invalid,
        "plugins": plugins,
    }
    payload["content_hash"] = _compute_index_content_hash(payload)
    return payload


def _read_index(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if not _index_valid(payload):
        return None
    return payload


def _index_valid(payload: dict[str, Any]) -> bool:
    required_keys = {
        "index_built_at",
        "total_plugins",
        "total_valid",
        "total_invalid",
        "plugins",
        "content_hash",
    }
    if not required_keys.issubset(payload.keys()):
        return False
    if not isinstance(payload.get("plugins"), dict):
        return False
    for entry in payload["plugins"].values():
        if not isinstance(entry, dict):
            return False
        if entry.get("status") not in {"VALID", "INVALID"}:
            return False
        if entry.get("plugin_type") not in {"indicator", "strategy"}:
            return False
        if not isinstance(entry.get("id"), str):
            return False
    content_hash = payload.get("content_hash")
    if not isinstance(content_hash, str):
        return False
    return content_hash == _compute_index_content_hash(payload)


def _entry_from_artifact(path: Path, plugin_type: str) -> tuple[dict[str, Any], str]:
    plugin_id = path.stem
    status = "INVALID"
    source_hash = ""
    checked_at = None
    name = None
    version = None
    category = None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = None
    if isinstance(payload, dict):
        status_value = payload.get("status")
        if status_value in {"VALID", "INVALID"}:
            status = status_value
        source_hash = payload.get("source_hash") or ""
        checked_at = payload.get("checked_at_utc")
        name = payload.get("name")
        version = payload.get("version")
        category = payload.get("category")
        payload_id = payload.get("id")
        if isinstance(payload_id, str) and payload_id:
            plugin_id = payload_id
    entry = {
        "id": plugin_id,
        "plugin_type": plugin_type,
        "status": status,
        "source_hash": source_hash,
        "checked_at_utc": checked_at,
        "name": name,
        "version": version,
        "category": category,
    }
    return entry, status


def _index_stale(payload: dict[str, Any], repo_root: Path, artifacts_root: Path) -> bool:
    candidates = discover_plugins(repo_root)
    candidate_map = {
        f"{candidate.plugin_type}:{candidate.plugin_id}": candidate for candidate in candidates
    }
    plugins = payload.get("plugins", {})
    if len(candidate_map) != len(plugins):
        return True

    for key, candidate in candidate_map.items():
        entry = plugins.get(key)
        if not isinstance(entry, dict):
            return True
        artifact_path = (
            artifacts_root
            / "plugin_validation"
            / candidate.plugin_type
            / f"{candidate.plugin_id}.json"
        )
        if not artifact_path.exists():
            return True
        current_hash = _hash_plugin_dir(candidate.plugin_dir)
        if current_hash is None:
            return True
        if entry.get("source_hash") != current_hash:
            return True

    for key in plugins.keys():
        if key not in candidate_map:
            return True

    return False


def _resolve_repo_root(artifacts_root: Path) -> Path:
    candidate = artifacts_root.parent
    if (candidate / "user_indicators").exists() or (candidate / "user_strategies").exists():
        return candidate
    cwd = Path.cwd()
    if (cwd / "user_indicators").exists() or (cwd / "user_strategies").exists():
        return cwd
    return candidate


def _active_payload(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry.get("id"),
        "name": entry.get("name"),
        "version": entry.get("version"),
        "category": entry.get("category"),
        "validated_at_utc": entry.get("checked_at_utc"),
        "fingerprint": entry.get("source_hash"),
    }


def _failed_payload(artifacts_root: Path, entry: dict[str, Any]) -> dict[str, Any]:
    details = _load_artifact_details(artifacts_root, entry)
    errors = _to_error_payload(details.get("reason_codes", []), details.get("reason_messages", []))
    return {
        "id": entry.get("id"),
        "status": entry.get("status"),
        "errors": errors,
        "validated_at_utc": entry.get("checked_at_utc"),
        "fingerprint": entry.get("source_hash"),
    }


def _load_artifact_details(artifacts_root: Path, entry: dict[str, Any]) -> dict[str, Any]:
    plugin_type = entry.get("plugin_type")
    plugin_id = entry.get("id")
    if not plugin_type or not plugin_id:
        return {"reason_codes": ["ARTIFACT_INVALID"], "reason_messages": ["Invalid entry."]}
    path = artifacts_root / "plugin_validation" / plugin_type / f"{plugin_id}.json"
    if not path.exists():
        return {"reason_codes": ["ARTIFACT_MISSING"], "reason_messages": ["Artifact missing."]}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "reason_codes": ["ARTIFACT_INVALID"],
            "reason_messages": [f"Artifact invalid: {exc}"],
        }
    if not isinstance(payload, dict):
        return {
            "reason_codes": ["ARTIFACT_INVALID"],
            "reason_messages": ["Artifact invalid."],
        }
    codes = payload.get("reason_codes")
    messages = payload.get("reason_messages")
    return {
        "reason_codes": codes if isinstance(codes, list) else [],
        "reason_messages": messages if isinstance(messages, list) else [],
    }


def _to_error_payload(codes: list[Any], messages: list[Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if len(codes) != len(messages):
        messages = list(messages) + ["" for _ in range(len(codes) - len(messages))]
    for code, message in zip(codes, messages):
        if not code:
            continue
        errors.append({"rule_id": str(code), "message": str(message or "")})
    return errors


def _hash_plugin_dir(plugin_dir: Path) -> str | None:
    hasher = sha256()
    if not plugin_dir.exists():
        return None
    try:
        for path in sorted(plugin_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(plugin_dir).as_posix()
            hasher.update(rel.encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(path.read_bytes())
    except OSError:
        return None
    return hasher.hexdigest()


def _compute_index_content_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        {
            "total_plugins": payload.get("total_plugins"),
            "total_valid": payload.get("total_valid"),
            "total_invalid": payload.get("total_invalid"),
            "plugins": payload.get("plugins"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def _index_lock_active(artifacts_root: Path) -> bool:
    lock_path = Path(artifacts_root) / "plugin_validation" / INDEX_LOCK_FILENAME
    lock = _IndexLock(lock_path)
    return lock.is_active()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc_iso(value: str) -> datetime | None:
    text = value.strip()
    if text.endswith("Z"):
        text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


@contextmanager
def _acquire_index_lock(artifacts_root: Path):
    lock_path = Path(artifacts_root) / "plugin_validation" / INDEX_LOCK_FILENAME
    lock = _IndexLock(lock_path)
    acquired = lock.acquire()
    try:
        yield acquired
    finally:
        if acquired:
            lock.release()


class _IndexLock:
    def __init__(self, lock_path: Path) -> None:
        self._lock_path = lock_path
        self._fd: int | None = None

    def acquire(self) -> bool:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        for _attempt in range(2):
            try:
                self._fd = os.open(
                    str(self._lock_path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
            except FileExistsError:
                if self._is_stale():
                    if not self._remove_lock():
                        return False
                    continue
                return False
            except OSError:
                return False
            payload = {"pid": os.getpid(), "created_at_utc": _utc_now_iso()}
            try:
                os.write(self._fd, json.dumps(payload).encode("utf-8"))
            except OSError:
                pass
            return True
        return False

    def is_active(self) -> bool:
        if not self._lock_path.exists():
            return False
        try:
            stale = self._is_stale()
        except Exception:
            try:
                return not self._mtime_stale()
            except Exception:
                return True
        if stale:
            self._remove_lock()
            return False
        return True

    def release(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        try:
            self._lock_path.unlink()
        except FileNotFoundError:
            return
        except OSError:
            return

    def _is_stale(self) -> bool:
        now = datetime.now(timezone.utc)
        try:
            raw = self._lock_path.read_text(encoding="utf-8")
            payload = json.loads(raw)
            created_at = payload.get("created_at_utc")
            if isinstance(created_at, str):
                parsed = _parse_utc_iso(created_at)
                if parsed is not None:
                    age = (now - parsed).total_seconds()
                    return age > INDEX_LOCK_TTL_SECONDS
        except (OSError, json.JSONDecodeError, AttributeError, TypeError):
            pass
        return self._mtime_stale()

    def _mtime_stale(self) -> bool:
        try:
            age = time.time() - self._lock_path.stat().st_mtime
        except OSError:
            return False
        return age > INDEX_LOCK_TTL_SECONDS

    def _remove_lock(self) -> bool:
        try:
            self._lock_path.unlink()
        except FileNotFoundError:
            return True
        except OSError:
            return False
        return True


def _count_artifact_files(artifacts_root: Path) -> int:
    root = artifacts_root / "plugin_validation"
    total = 0
    for plugin_type in ("indicator", "strategy"):
        folder = root / plugin_type
        if not folder.exists():
            continue
        total += len(list(folder.glob("*.json")))
    return total


def _empty_index() -> dict[str, Any]:
    return {
        "index_built_at": None,
        "total_plugins": 0,
        "total_valid": 0,
        "total_invalid": 0,
        "plugins": {},
        "content_hash": "",
    }

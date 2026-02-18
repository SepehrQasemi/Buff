from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from .canonical import write_canonical_json
from .paths import is_within_root, user_root, user_runs_root, validate_user_id

REGISTRY_FILENAME = "index.json"
REGISTRY_SCHEMA_VERSION = "1.0.0"
REGISTRY_LOCK_FILENAME = ".registry.lock"
REGISTRY_LOCK_TIMEOUT_SECONDS = 2.0

REQUIRED_ARTIFACTS = (
    "manifest.json",
    "config.json",
    "metrics.json",
    "equity_curve.json",
    "decision_records.jsonl",
)

TIMELINE_ARTIFACTS = (
    "timeline.json",
    "timeline_events.json",
    "risk_timeline.json",
    "selector_trace.json",
)

OHLCV_PRIMARY_ARTIFACTS = (
    "ohlcv.parquet",
    "ohlcv_1m.parquet",
    "ohlcv.jsonl",
    "ohlcv_1m.jsonl",
)

JSON_VALIDATION_ARTIFACTS = (
    "manifest.json",
    "metrics.json",
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


def _runs_path(user_root_path: Path) -> Path:
    return user_root_path / "runs"


def _registry_path(user_root_path: Path) -> Path:
    return user_root_path / REGISTRY_FILENAME


def _load_registry_payload(user_root_path: Path) -> dict[str, Any]:
    path = _registry_path(user_root_path)
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


def _utc_now_iso() -> str:
    text = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    if text.endswith("+00:00"):
        return text[:-6] + "Z"
    return text


def _manifest_path(run_id: str) -> str:
    return f"runs/{run_id}/manifest.json"


def _artifacts_present(run_dir: Path) -> list[str]:
    items = [child.name for child in run_dir.iterdir() if child.is_file()]
    return sorted(items)


def _resolve_trades_artifact(artifacts_present: set[str]) -> str | None:
    if "trades.parquet" in artifacts_present:
        return "trades.parquet"
    if "trades.jsonl" in artifacts_present:
        return "trades.jsonl"
    return None


def _resolve_ohlcv_artifact(run_dir: Path, artifacts_present: set[str]) -> str | None:
    for name in OHLCV_PRIMARY_ARTIFACTS:
        if name in artifacts_present:
            return name
    for name in sorted(artifacts_present):
        if name.startswith("ohlcv_") and (name.endswith(".parquet") or name.endswith(".jsonl")):
            return name
    for candidate in sorted(run_dir.glob("ohlcv_*.parquet")):
        if candidate.is_file():
            return candidate.name
    for candidate in sorted(run_dir.glob("ohlcv_*.jsonl")):
        if candidate.is_file():
            return candidate.name
    return None


def _resolve_timeline_artifact(artifacts_present: set[str]) -> str | None:
    for name in TIMELINE_ARTIFACTS:
        if name in artifacts_present:
            return name
    return None


def _json_parse_status(path: Path) -> tuple[str, bool]:
    if not path.exists():
        return "missing", False
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "invalid", True
    return "ok", False


def _evaluate_artifacts(run_dir: Path) -> dict[str, Any]:
    artifacts_present = _artifacts_present(run_dir)
    present_set = set(artifacts_present)

    required_checks: dict[str, dict[str, Any]] = {}
    missing_artifacts: list[str] = []
    for name in REQUIRED_ARTIFACTS:
        status = "ok" if name in present_set else "missing"
        required_checks[name] = {"status": status}
        if status == "missing":
            missing_artifacts.append(name)

    trades_source = _resolve_trades_artifact(present_set)
    required_checks["trades"] = {
        "status": "ok" if trades_source else "missing",
        "source": trades_source,
    }
    if trades_source is None:
        missing_artifacts.append("trades")

    ohlcv_source = _resolve_ohlcv_artifact(run_dir, present_set)
    required_checks["ohlcv"] = {
        "status": "ok" if ohlcv_source else "missing",
        "source": ohlcv_source,
    }
    if ohlcv_source is None:
        missing_artifacts.append("ohlcv")

    timeline_source = _resolve_timeline_artifact(present_set)
    if timeline_source is not None:
        timeline_required_status = "artifact"
    elif "decision_records.jsonl" in present_set:
        timeline_required_status = "derived"
    else:
        timeline_required_status = "missing"
    required_checks["timeline"] = {"status": timeline_required_status, "source": timeline_source}
    if timeline_required_status == "missing":
        missing_artifacts.append("timeline")

    json_checks: dict[str, dict[str, Any]] = {}
    invalid_artifacts: list[str] = []
    for name in JSON_VALIDATION_ARTIFACTS:
        status, invalid = _json_parse_status(run_dir / name)
        json_checks[name] = {"status": status}
        if invalid:
            invalid_artifacts.append(name)
        if status == "invalid" and name in required_checks:
            required_checks[name]["status"] = "invalid"

    if timeline_source is not None:
        timeline_status, timeline_invalid = _json_parse_status(run_dir / timeline_source)
        json_checks["timeline"] = {"status": timeline_status, "source": timeline_source}
        if timeline_invalid:
            invalid_artifacts.append(timeline_source)
            required_checks["timeline"]["status"] = "invalid"
    else:
        json_checks["timeline"] = {"status": timeline_required_status, "source": timeline_source}

    return {
        "artifacts_present": artifacts_present,
        "missing_artifacts": sorted(set(missing_artifacts)),
        "invalid_artifacts": sorted(set(invalid_artifacts)),
        "checks": {"required": required_checks, "json_parse": json_checks},
    }


def _derive_status_and_health(
    missing_artifacts: list[str],
    invalid_artifacts: list[str],
    manifest: dict[str, Any],
    *,
    fallback_status: str | None = None,
) -> tuple[str, str]:
    if missing_artifacts:
        return "CORRUPTED", "CORRUPTED"
    manifest_status = manifest.get("status")
    if isinstance(manifest_status, str) and manifest_status.strip():
        status = manifest_status
    elif fallback_status and str(fallback_status).strip():
        status = str(fallback_status)
    else:
        status = "OK"
    if invalid_artifacts:
        return status, "DEGRADED"
    return status, "HEALTHY"


def _extract_owner_user_id(manifest: dict[str, Any], fallback_user_id: str | None) -> str | None:
    meta = manifest.get("meta")
    if isinstance(meta, dict):
        owner = meta.get("owner_user_id")
        if isinstance(owner, str):
            owner = owner.strip()
            if owner:
                return owner
    return fallback_user_id


def build_registry_entry(
    run_dir: Path,
    manifest: dict[str, Any],
    *,
    user_id: str | None = None,
    fallback_status: str | None = None,
    migrated_from_legacy: bool | None = None,
) -> dict[str, Any]:
    run_id = str(manifest.get("run_id") or run_dir.name)
    artifact_eval = _evaluate_artifacts(run_dir)
    status, health = _derive_status_and_health(
        artifact_eval["missing_artifacts"],
        artifact_eval["invalid_artifacts"],
        manifest,
        fallback_status=fallback_status,
    )

    created_at = manifest.get("created_at")
    if not isinstance(created_at, str) or not created_at.strip():
        created_at = _utc_now_iso()
    owner_user_id = _extract_owner_user_id(manifest, user_id)

    entry = {
        "run_id": run_id,
        "created_at": created_at,
        "owner_user_id": owner_user_id,
        "symbol": (manifest.get("data") or {}).get("symbol"),
        "timeframe": (manifest.get("data") or {}).get("timeframe"),
        "status": status,
        "health": health,
        "manifest_path": _manifest_path(run_id),
        "artifacts_present": artifact_eval["artifacts_present"],
        "inputs_hash": manifest.get("inputs_hash"),
        "strategy_id": (manifest.get("strategy") or {}).get("id"),
        "missing_artifacts": artifact_eval["missing_artifacts"],
        "invalid_artifacts": artifact_eval["invalid_artifacts"],
        "checks": artifact_eval["checks"],
        "last_verified_at": _utc_now_iso(),
    }
    entry_meta: dict[str, Any] = {}
    if owner_user_id:
        entry_meta["owner_user_id"] = owner_user_id
    if migrated_from_legacy is not None:
        entry_meta["migrated_from_legacy"] = bool(migrated_from_legacy)
    else:
        manifest_meta = manifest.get("meta")
        if isinstance(manifest_meta, dict) and isinstance(
            manifest_meta.get("migrated_from_legacy"), bool
        ):
            entry_meta["migrated_from_legacy"] = bool(manifest_meta["migrated_from_legacy"])
    if entry_meta:
        entry["meta"] = entry_meta
    return entry


def _load_manifest_from_run_dir(run_dir: Path) -> dict[str, Any]:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _is_candidate_run_dir(run_dir: Path) -> bool:
    if not run_dir.is_dir():
        return False
    name = run_dir.name.strip()
    if not name or name.startswith("."):
        return False
    lowered = name.lower()
    if lowered in {"inputs", "__pycache__", "tmp", "temp", "users"}:
        return False
    if lowered.startswith("tmp_") or lowered.startswith("tmp-"):
        return False
    if lowered.startswith(".tmp_") or lowered.startswith(".tmp-"):
        return False
    has_sentinel = (run_dir / "manifest.json").exists() or (
        run_dir / "decision_records.jsonl"
    ).exists()
    if not has_sentinel:
        return False
    return True


def _missing_run_dir_entry(
    run_id: str,
    existing: dict[str, Any],
    *,
    owner_user_id: str | None,
) -> dict[str, Any]:
    created_at = existing.get("created_at")
    if not isinstance(created_at, str):
        created_at = _utc_now_iso()
    symbol = existing.get("symbol")
    if not isinstance(symbol, str):
        symbol = None
    timeframe = existing.get("timeframe")
    if not isinstance(timeframe, str):
        timeframe = None
    inputs_hash = existing.get("inputs_hash")
    if not isinstance(inputs_hash, str):
        inputs_hash = None
    strategy_id = existing.get("strategy_id")
    if not isinstance(strategy_id, str):
        strategy_id = None
    entry = {
        "run_id": run_id,
        "created_at": created_at,
        "owner_user_id": owner_user_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "status": "CORRUPTED",
        "health": "CORRUPTED",
        "manifest_path": _manifest_path(run_id),
        "artifacts_present": [],
        "inputs_hash": inputs_hash,
        "strategy_id": strategy_id,
        "missing_artifacts": ["run_dir"],
        "invalid_artifacts": [],
        "checks": {"required": {"run_dir": {"status": "missing"}}, "json_parse": {}},
        "last_verified_at": _utc_now_iso(),
    }
    entry_meta = existing.get("meta")
    if isinstance(entry_meta, dict):
        if isinstance(entry_meta.get("migrated_from_legacy"), bool):
            entry["meta"] = {"migrated_from_legacy": entry_meta["migrated_from_legacy"]}
            if owner_user_id:
                entry["meta"]["owner_user_id"] = owner_user_id
    return entry


def _sorted_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [entry for entry in runs if isinstance(entry, dict)],
        key=lambda item: str(item.get("run_id") or ""),
    )


def _user_id_from_user_root(user_root_path: Path) -> str | None:
    candidate = user_root_path.name
    try:
        return validate_user_id(candidate)
    except ValueError:
        return None


def upsert_registry_entry(
    user_root_path: Path,
    run_dir: Path,
    manifest: dict[str, Any],
    *,
    migrated_from_legacy: bool | None = None,
) -> dict[str, Any]:
    registry = _load_registry_payload(user_root_path)
    runs = registry.get("runs", [])
    owner_user_id = _user_id_from_user_root(user_root_path)
    entry = build_registry_entry(
        run_dir,
        manifest,
        user_id=owner_user_id,
        migrated_from_legacy=migrated_from_legacy,
    )
    replaced = False
    for idx, existing in enumerate(runs):
        if isinstance(existing, dict) and existing.get("run_id") == entry["run_id"]:
            runs[idx] = entry
            replaced = True
            break
    if not replaced:
        runs.append(entry)
    registry["runs"] = _sorted_runs(runs)
    registry["generated_at"] = _utc_now_iso()
    _write_registry_payload(user_root_path, registry)
    return entry


def reconcile_registry(user_root_path: Path) -> dict[str, Any]:
    registry = _load_registry_payload(user_root_path)
    runs = registry.get("runs")
    existing_entries = runs if isinstance(runs, list) else []

    runs_path = _runs_path(user_root_path)
    runs_path.mkdir(parents=True, exist_ok=True)
    owner_user_id = _user_id_from_user_root(user_root_path)

    reconciled: list[dict[str, Any]] = []
    seen_run_ids: set[str] = set()
    updated = False

    for entry in existing_entries:
        if not isinstance(entry, dict):
            updated = True
            continue
        run_id_raw = entry.get("run_id")
        run_id = str(run_id_raw).strip() if run_id_raw is not None else ""
        if not run_id or run_id in seen_run_ids:
            updated = True
            continue
        seen_run_ids.add(run_id)
        run_dir = (runs_path / run_id).resolve()
        if not is_within_root(run_dir, runs_path) or not run_dir.exists() or not run_dir.is_dir():
            rebuilt = _missing_run_dir_entry(run_id, entry, owner_user_id=owner_user_id)
        else:
            manifest = _load_manifest_from_run_dir(run_dir)
            status_hint = entry.get("status")
            fallback_status = str(status_hint) if isinstance(status_hint, str) else None
            rebuilt = build_registry_entry(
                run_dir,
                manifest,
                user_id=owner_user_id,
                fallback_status=fallback_status,
            )
        if rebuilt != entry:
            updated = True
        reconciled.append(rebuilt)

    for child in sorted(runs_path.iterdir(), key=lambda item: item.name):
        if not _is_candidate_run_dir(child):
            continue
        run_dir = child.resolve()
        if not is_within_root(run_dir, runs_path):
            continue
        run_id = child.name
        if run_id in seen_run_ids:
            continue
        manifest = _load_manifest_from_run_dir(run_dir)
        reconciled.append(build_registry_entry(run_dir, manifest, user_id=owner_user_id))
        seen_run_ids.add(run_id)
        updated = True

    sorted_runs = _sorted_runs(reconciled)
    if sorted_runs != registry.get("runs"):
        updated = True
    registry["runs"] = sorted_runs
    if updated or registry.get("generated_at") is None:
        registry["generated_at"] = _utc_now_iso()
        _write_registry_payload(user_root_path, registry)
    return registry


def load_registry(user_root_path: Path) -> dict[str, Any]:
    return _load_registry_payload(user_root_path)


def get_registry_entry(user_root_path: Path, run_id: str) -> dict[str, Any] | None:
    registry = _load_registry_payload(user_root_path)
    runs = registry.get("runs", [])
    for entry in runs:
        if isinstance(entry, dict) and entry.get("run_id") == run_id:
            return entry
    return None


def _write_registry_payload(user_root_path: Path, payload: dict[str, Any]) -> None:
    user_root_path.mkdir(parents=True, exist_ok=True)
    path = _registry_path(user_root_path)
    tmp_path = path.with_suffix(".tmp")
    write_canonical_json(tmp_path, payload)
    os.replace(tmp_path, path)
    _fsync_dir(user_root_path)


def compute_inputs_hash(canonical_bytes: bytes) -> str:
    return sha256(canonical_bytes).hexdigest()


def lock_registry(user_root_path: Path) -> RegistryLock:
    return RegistryLock(user_root_path / REGISTRY_LOCK_FILENAME)


def list_legacy_run_dirs(base_runs_root: Path) -> list[Path]:
    if not base_runs_root.exists() or not base_runs_root.is_dir():
        return []
    legacy_dirs: list[Path] = []
    for child in sorted(base_runs_root.iterdir(), key=lambda item: item.name):
        if child.name == "users":
            continue
        if _is_candidate_run_dir(child):
            legacy_dirs.append(child.resolve())
    return legacy_dirs


def has_legacy_runs(base_runs_root: Path) -> bool:
    return bool(list_legacy_run_dirs(base_runs_root))


def migrate_legacy_runs(base_runs_root: Path, default_user_id: str) -> dict[str, Any]:
    normalized_user = validate_user_id(default_user_id)
    target_user_root = user_root(base_runs_root, normalized_user)
    target_runs_root = user_runs_root(base_runs_root, normalized_user)
    target_runs_root.mkdir(parents=True, exist_ok=True)

    migrated_ids: list[str] = []
    lock = lock_registry(target_user_root)
    with lock:
        for source_dir in list_legacy_run_dirs(base_runs_root):
            run_id = source_dir.name
            destination_dir = (target_runs_root / run_id).resolve()
            if not is_within_root(destination_dir, target_runs_root):
                raise RuntimeError(f"MIGRATION_INVALID_RUN_ID:{run_id}")
            if destination_dir.exists():
                raise RuntimeError(f"MIGRATION_CONFLICT:{run_id}")

            os.replace(source_dir, destination_dir)
            manifest = _load_manifest_from_run_dir(destination_dir)
            if not isinstance(manifest, dict):
                manifest = {}
            if not str(manifest.get("run_id") or "").strip():
                manifest["run_id"] = run_id
            if not str(manifest.get("created_at") or "").strip():
                manifest["created_at"] = _utc_now_iso()
            meta = manifest.get("meta")
            if not isinstance(meta, dict):
                meta = {}
            meta["owner_user_id"] = normalized_user
            meta["migrated_from_legacy"] = True
            manifest["meta"] = meta
            write_canonical_json(destination_dir / "manifest.json", manifest)

            upsert_registry_entry(
                target_user_root,
                destination_dir,
                manifest,
                migrated_from_legacy=True,
            )
            migrated_ids.append(run_id)

    return {
        "user_id": normalized_user,
        "migrated_run_ids": sorted(migrated_ids),
        "count": len(migrated_ids),
    }
